#!/usr/bin/env bash
# Tests for build-javadoc-site.sh. Self-contained: builds synthetic Maven trees and javadoc jars
# in a temp directory, runs the real script against them, and asserts on the site it produces.
# Fixture jars are built with python3 rather than `zip` so this runs unchanged on the CI runner
# and on a Windows git-bash checkout.
set -uo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
under_test="$script_dir/build-javadoc-site.sh"
tmp_root="$(mktemp -d)"
trap 'rm -rf "$tmp_root"' EXIT

passed=0 failed=0
ok()   { printf '  ok   %s\n' "$1"; passed=$((passed + 1)); }
bad()  { printf '  FAIL %s\n' "$1"; failed=$((failed + 1)); }
check() { if [[ $1 == 0 ]]; then ok "$2"; else bad "$2"; fi; }

# A fixture is a throwaway repository root with the script under test copied into place, so the
# script's own "repo root = my directory/../.." resolution points at the fixture.
new_fixture() {
  local fx="$tmp_root/$1"
  mkdir -p "$fx/.github/scripts"
  cp "$under_test" "$script_dir/api_additions.py" "$fx/.github/scripts/"
  printf '%s' "$fx"
}

# make_jar <path> <entry>[ <entry>...] - each entry is NAME=CONTENT.
make_jar() {
  local out="$1"; shift
  mkdir -p "$(dirname "$out")"
  python3 - "$out" "$@" <<'PY'
import sys, zipfile
out, entries = sys.argv[1], sys.argv[2:]
with zipfile.ZipFile(out, "w") as zf:
    for e in entries:
        name, _, content = e.partition("=")
        zf.writestr(name, content)
PY
}

# publish <fixture> <group-path> <artifactId> <version> - a realistic javadoc jar plus the deep
# file and subpath-sensitive assets a real javadoc tree has.
publish() {
  local fx="$1" group="$2" artifact="$3" version="$4"
  make_jar "$fx/$group/$artifact/$version/$artifact-$version-javadoc.jar" \
    "index.html=<html>$artifact $version</html>" \
    "stylesheet.css=body{}" \
    "search.js=//search" \
    "element-list=net.beltaria" \
    "net/beltaria/Deep.html=<html>deep</html>" \
    "META-INF/MANIFEST.MF=Manifest-Version: 1.0"
}

metadata() {
  local fx="$1" group="$2" artifact="$3" body="$4"
  printf '<metadata>\n  <versioning>\n%s\n  </versioning>\n</metadata>\n' "$body" \
    > "$fx/$group/$artifact/maven-metadata.xml"
}

run_site() { ( cd "$1" && SITE_DIR=_site bash .github/scripts/build-javadoc-site.sh ); }

echo "happy path"
fx="$(new_fixture happy)"
publish "$fx" net/beltaria beltariaspigot-api 1.8.8-R0.1-SNAPSHOT
metadata "$fx" net/beltaria beltariaspigot-api '    <latest>1.8.8-R0.1-SNAPSHOT</latest>'
out="$(run_site "$fx" 2>&1)"; check $? "script succeeds"
site="$fx/_site"
[[ -f $site/beltariaspigot-api/1.8.8-R0.1-SNAPSHOT/index.html ]]; check $? "unpacks to /<artifactId>/<version>/"
[[ -f $site/beltariaspigot-api/latest/index.html ]];              check $? "creates the latest alias"
# The alias must be a real copy: this deep file is exactly what a README or -link URL targets,
# and is the thing a meta-refresh redirect would have 404'd.
[[ -f $site/beltariaspigot-api/latest/net/beltaria/Deep.html ]];  check $? "latest answers deep links"
[[ -f $site/beltariaspigot-api/latest/stylesheet.css && -f $site/beltariaspigot-api/latest/search.js \
   && -f $site/beltariaspigot-api/latest/element-list ]];         check $? "keeps subpath-sensitive assets"
[[ ! -d $site/beltariaspigot-api/latest/META-INF ]];              check $? "strips META-INF"
grep -q 'net.beltaria:beltariaspigot-api' "$site/index.html";     check $? "index names the coordinates"
grep -q 'href="./beltariaspigot-api/latest/"' "$site/index.html"; check $? "index links latest"
grep -q '1.8.8-R0.1-SNAPSHOT' "$site/index.html";                 check $? "index lists the version"
grep -q 'unpacked net.beltaria:beltariaspigot-api:1.8.8-R0.1-SNAPSHOT' <<<"$out"; check $? "logs what it unpacked"

echo "latest resolution"
fx="$(new_fixture release-wins)"
publish "$fx" net/beltaria api 1.0
publish "$fx" net/beltaria api 2.0
publish "$fx" net/beltaria api 3.0-SNAPSHOT
# A repo with both: <release> is the current stable, <latest> may be a newer snapshot. Maven
# treats <release> as the answer to "what should I use", and so should the alias.
metadata "$fx" net/beltaria api '    <latest>3.0-SNAPSHOT</latest>
    <release>2.0</release>'
run_site "$fx" >/dev/null 2>&1; check $? "script succeeds"
[[ -f $fx/_site/api/latest/index.html ]] && grep -q 'api 2.0' "$fx/_site/api/latest/index.html"
check $? "<release> beats <latest>"
grep -q 'href="./api/3.0-SNAPSHOT/"' "$fx/_site/index.html"; check $? "index still lists every version"

fx="$(new_fixture no-metadata)"
publish "$fx" net/beltaria api 1.9
publish "$fx" net/beltaria api 1.10
run_site "$fx" >/dev/null 2>&1; check $? "script succeeds without maven-metadata.xml"
# sort -V, not lexicographic: 1.10 > 1.9.
grep -q 'api 1.10' "$fx/_site/api/latest/index.html"; check $? "falls back to the highest version"

fx="$(new_fixture stale-metadata)"
publish "$fx" net/beltaria api 1.0
metadata "$fx" net/beltaria api '    <latest>9.9-never-published</latest>'
run_site "$fx" >/dev/null 2>&1; check $? "script succeeds with metadata naming a missing version"
grep -q 'api 1.0' "$fx/_site/api/latest/index.html"; check $? "ignores a version that shipped no javadoc"

echo "refusals"
fx="$(new_fixture empty)"
mkdir -p "$fx/net/beltaria"
! run_site "$fx" >/dev/null 2>&1; check $? "fails when no javadoc jar exists"

fx="$(new_fixture no-net)"
! run_site "$fx" >/dev/null 2>&1; check $? "fails when net/ is absent"

fx="$(new_fixture collision)"
publish "$fx" net/beltaria api 1.0
publish "$fx" net/other   api 1.0
err="$(run_site "$fx" 2>&1)"; ! [[ $? == 0 ]]; check $? "fails on an artifactId published under two groups"
grep -q "published under both" <<<"$err"; check $? "explains the collision"

fx="$(new_fixture traversal)"
make_jar "$fx/net/beltaria/api/1.0/api-1.0-javadoc.jar" \
  'index.html=<html></html>' '../../../evil.html=<html>pwned</html>'
err="$(run_site "$fx" 2>&1)"; ! [[ $? == 0 ]]; check $? "fails on a path-traversal entry"
[[ ! -f $tmp_root/evil.html && ! -f $fx/evil.html ]]; check $? "writes nothing outside the site dir"

fx="$(new_fixture bad-version)"
publish "$fx" net/beltaria api 1.0
mkdir -p -- "$fx/net/beltaria/api/-nope"
cp "$fx/net/beltaria/api/1.0/api-1.0-javadoc.jar" "$fx/net/beltaria/api/-nope/api--nope-javadoc.jar"
! run_site "$fx" >/dev/null 2>&1; check $? "fails on a version outside the safe charset"

echo "api additions"
fx="$(new_fixture additions)"
publish "$fx" net/beltaria api 1.0
# A sources jar carrying the markers is what becomes the "What BeltariaSpigot adds" section.
make_jar "$fx/net/beltaria/api/1.0/api-1.0-sources.jar" \
  'org/bukkit/World.java=package org.bukkit;
public interface World {
    // BeltariaSpigot start - async chunks
    public Chunk getChunkAtAsync(int x, int z);
    // BeltariaSpigot end
}'
run_site "$fx" >/dev/null 2>&1; check $? "script succeeds with a sources jar"
grep -q "What BeltariaSpigot adds" "$fx/_site/index.html"; check $? "renders the additions section"
grep -q "getChunkAtAsync(int, int)" "$fx/_site/index.html"; check $? "lists the added member"
grep -q "async chunks" "$fx/_site/index.html";             check $? "shows the marker rationale"

fx="$(new_fixture no-sources)"
publish "$fx" net/beltaria api 1.0
run_site "$fx" >/dev/null 2>&1; check $? "script succeeds without a sources jar"
! grep -q "What BeltariaSpigot adds" "$fx/_site/index.html"; check $? "omits the section when there is nothing to say"

printf '\n%d passed, %d failed\n' "$passed" "$failed"
[[ $failed -eq 0 ]]
