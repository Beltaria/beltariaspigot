#!/usr/bin/env python3
"""Tests for api_additions.py.

The parser is a heuristic over Java source, so the cases here are the shapes Bukkit's API
actually uses: interfaces with brace-on-same-line, nested classes with brace-on-next-line,
method bodies that throw, marker rationales wrapping over several comment lines, and overload
sets where only some overloads are Beltaria's.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import api_additions as m  # noqa: E402


class TypeAndParamParsing(unittest.TestCase):
    def test_simple_type_drops_the_package(self):
        self.assertEqual(m.simple_type("org.bukkit.Location"), "Location")
        self.assertEqual(m.simple_type("int"), "int")

    def test_simple_type_keeps_arrays(self):
        self.assertEqual(m.simple_type("java.lang.String[]"), "String[]")
        self.assertEqual(m.simple_type("byte[][]"), "byte[][]")

    def test_split_params_drops_names_and_annotations(self):
        self.assertEqual(m.split_params("int x, ItemStack ingredient"), ["int", "ItemStack"])
        self.assertEqual(m.split_params("@NotNull Location location, boolean gen"),
                         ["Location", "boolean"])

    def test_split_params_handles_generics_and_varargs(self):
        # A comma inside <> must not split the parameter list.
        self.assertEqual(m.split_params("Map<String, Integer> m, String s"), ["Map", "String"])
        self.assertEqual(m.split_params("String... parts"), ["String[]"])

    def test_split_params_empty(self):
        self.assertEqual(m.split_params(""), [])
        self.assertEqual(m.split_params("   "), [])


class StripCode(unittest.TestCase):
    def test_braces_in_strings_are_not_counted(self):
        code, _ = m.strip_code('String s = "{{{";', False)
        self.assertNotIn("{", code)

    def test_line_comment_is_dropped(self):
        code, _ = m.strip_code("int x = 1; // } } }", False)
        self.assertNotIn("}", code)

    def test_block_comment_spans_lines(self):
        code, state = m.strip_code("/* {{ ", False)
        self.assertTrue(state)
        self.assertNotIn("{", code)
        code, state = m.strip_code(" still comment {{ */ int y;", state)
        self.assertFalse(state)
        self.assertNotIn("{", code)
        self.assertIn("int y;", code)

    def test_escaped_quote_does_not_end_the_literal(self):
        code, _ = m.strip_code('String s = "a\\"{"; int z;', False)
        self.assertNotIn("{", code)
        self.assertIn("int z;", code)


class FirstSentence(unittest.TestCase):
    def test_takes_one_sentence_and_trims_the_period(self):
        self.assertEqual(m.first_sentence("urgent chunk requests. And more prose here."),
                         "urgent chunk requests")

    def test_passes_through_when_there_is_no_period(self):
        self.assertEqual(m.first_sentence("custom string tag API"), "custom string tag API")

    def test_collapses_whitespace_from_joined_comment_lines(self):
        self.assertEqual(m.first_sentence("a rationale   that\n wrapped"),
                         "a rationale that wrapped")


INTERFACE_SRC = """package org.bukkit;

public interface World {
    public Chunk getChunkAt(int x, int z);

    // BeltariaSpigot start - async chunks, with Paper's exact signatures
    // so plugins written against modern Paper compile unchanged. More prose.
    /** javadoc here */
    public java.util.concurrent.CompletableFuture<Chunk> getChunkAtAsync(int x, int z);
    public java.util.concurrent.CompletableFuture<Chunk> getChunkAtAsync(Location location);
    // BeltariaSpigot end

    public boolean isChunkLoaded(int x, int z);
}
"""

NESTED_SRC = """package org.bukkit.inventory.meta;

public interface ItemMeta {
    public class Spigot
    {
        // BeltariaSpigot start - custom string tag API
        public void setStringTag(String key, String value)
        {
            throw new UnsupportedOperationException( "Not supported yet." );
        }

        public String getStringTag(String key)
        {
            throw new UnsupportedOperationException( "Not supported yet." );
        }
        // BeltariaSpigot end
    }
}
"""

BEHAVIOUR_SRC = """package org.bukkit.command.defaults;

public class ReloadCommand {
    public boolean execute() {
        // BeltariaSpigot start - the command stays registered, but only to explain itself
        sender.sendMessage("no");
        return true;
        // BeltariaSpigot end
    }
}
"""

NEW_TYPE_SRC = """package org.spigotmc.event.player;

// BeltariaSpigot start - Paper's armor change event, backported
public class PlayerArmorChangeEvent extends PlayerEvent {
    public SlotType getSlotType() { return slotType; }
}
// BeltariaSpigot end
"""


class ScanFile(unittest.TestCase):
    def scan(self, entry, src):
        return m.scan_file(entry, src)

    def test_picks_up_only_members_inside_the_block(self):
        found = self.scan("org/bukkit/World.java", INTERFACE_SRC)
        self.assertEqual([a.display for a in found],
                         ["getChunkAtAsync(int, int)", "getChunkAtAsync(Location)"])

    def test_records_package_and_owner(self):
        found = self.scan("org/bukkit/World.java", INTERFACE_SRC)
        self.assertEqual(found[0].package, "org.bukkit")
        self.assertEqual(found[0].owner, "World")

    def test_joins_the_wrapped_rationale_and_keeps_one_sentence(self):
        found = self.scan("org/bukkit/World.java", INTERFACE_SRC)
        self.assertEqual(found[0].why,
                         "async chunks, with Paper's exact signatures so plugins written "
                         "against modern Paper compile unchanged")

    def test_nested_class_with_brace_on_the_next_line(self):
        # ItemMeta.Spigot is the real shape: javadoc renders it as ItemMeta.Spigot.html, so
        # getting the owner wrong here means every link in that section 404s.
        found = self.scan("org/bukkit/inventory/meta/ItemMeta.java", NESTED_SRC)
        self.assertEqual([a.owner for a in found], ["ItemMeta.Spigot", "ItemMeta.Spigot"])
        self.assertEqual([a.display for a in found],
                         ["setStringTag(String, String)", "getStringTag(String)"])

    def test_method_bodies_are_not_mistaken_for_declarations(self):
        found = self.scan("org/bukkit/inventory/meta/ItemMeta.java", NESTED_SRC)
        self.assertNotIn("UnsupportedOperationException", " ".join(a.name for a in found))

    def test_block_declaring_nothing_is_a_behaviour_change(self):
        found = self.scan("org/bukkit/command/defaults/ReloadCommand.java", BEHAVIOUR_SRC)
        self.assertEqual([a.kind for a in found], ["behaviour"])
        self.assertEqual(found[0].why, "the command stays registered, but only to explain itself")

    def test_type_declared_inside_a_block_is_a_new_type(self):
        found = self.scan("org/spigotmc/event/player/PlayerArmorChangeEvent.java", NEW_TYPE_SRC)
        kinds = {a.kind: a for a in found}
        self.assertIn("type", kinds)
        self.assertEqual(kinds["type"].name, "PlayerArmorChangeEvent")

    def test_unmarked_file_yields_nothing(self):
        self.assertEqual(self.scan("org/bukkit/Chunk.java",
                                   "package org.bukkit;\npublic interface Chunk { int getX(); }\n"),
                         [])


WORLD_HTML = """<html>
<section class="detail" id="getChunkAt(int,int)"></section>
<section class="detail" id="getChunkAtAsync(int,int)"></section>
<section class="detail" id="getChunkAtAsync(org.bukkit.Location)"></section>
<section class="detail" id="getChunkAtAsync(org.bukkit.Location,org.bukkit.World.ChunkLoadCallback)"></section>
<section class="detail" id="&lt;init&gt;()"></section>
</html>
"""


class AnchorsAndRender(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        page = self.root / "org" / "bukkit" / "World.html"
        page.parent.mkdir(parents=True)
        page.write_text(WORLD_HTML, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_anchors_are_keyed_by_simple_param_types(self):
        anchors = m.javadoc_anchors(self.root / "org" / "bukkit" / "World.html")
        self.assertEqual(anchors[("getChunkAtAsync", ("Location",))],
                         "getChunkAtAsync(org.bukkit.Location)")

    def test_constructors_are_skipped(self):
        anchors = m.javadoc_anchors(self.root / "org" / "bukkit" / "World.html")
        self.assertFalse([k for k in anchors if k[0].startswith("&lt;")])

    def test_render_links_the_right_overload(self):
        html = m.render(m.scan_file("org/bukkit/World.java", INTERFACE_SRC), self.root, "./x/latest")
        self.assertIn("World.html#getChunkAtAsync(int,int)", html)
        self.assertIn("World.html#getChunkAtAsync(org.bukkit.Location)", html)
        # The ChunkLoadCallback overload is upstream's, not Beltaria's - it must not appear.
        self.assertNotIn("ChunkLoadCallback", html)

    def test_render_flags_members_with_no_anchor(self):
        src = INTERFACE_SRC.replace("getChunkAtAsync(Location location)", "notInJavadoc(int q)")
        html = m.render(m.scan_file("org/bukkit/World.java", src), self.root, "./x/latest")
        self.assertIn("not in the javadoc", html)

    def test_render_is_empty_without_additions(self):
        self.assertEqual(m.render([], self.root, "./x/latest"), "")

    def test_behaviour_changes_are_listed_once_per_type(self):
        doubled = BEHAVIOUR_SRC.replace(
            "        return true;\n",
            "        return true;\n        // BeltariaSpigot end\n"
            "        // BeltariaSpigot start - second block\n        int y = 1;\n")
        found = m.scan_file("org/bukkit/command/defaults/ReloadCommand.java", doubled)
        html = m.render(found, self.root, "./x/latest")
        self.assertEqual(html.count("ReloadCommand"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
