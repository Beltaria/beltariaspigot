#!/usr/bin/env bash
# Builds the GitHub Pages site for Beltaria/beltariaspigot out of the javadoc jars committed under net/.
# Nothing here is artifact-specific: every net/<group...>/<artifactId>/<version>/ directory
# holding a *-javadoc.jar becomes /<artifactId>/<version>/ on the site, and each artifact also
# gets a /<artifactId>/latest/ alias. Publishing a new artifact or a new version needs no change
# to this file.
set -euo pipefail

SITE_DIR="${SITE_DIR:-_site}"
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# unzip ships in the ubuntu-latest runner image, so no setup step is needed - but fail with a
# readable message rather than "command not found" three levels into a loop.
command -v unzip >/dev/null || { echo "unzip is required but not installed" >&2; exit 1; }
command -v python3 >/dev/null || { echo "python3 is required but not installed" >&2; exit 1; }
[[ -d net ]] || { echo "no net/ directory - nothing to publish" >&2; exit 1; }

rm -rf "$SITE_DIR"
mkdir -p "$SITE_DIR"

# Maven coordinates only ever contain these characters. Anything else in a path component is
# either a corrupt publish or an attempt to escape $SITE_DIR, and is refused. This doubles as the
# guarantee that coordinates can be interpolated into the HTML below without escaping.
readonly SAFE='^[A-Za-z0-9][A-Za-z0-9._-]*$'

mapfile -t javadoc_jars < <(find net -type f -name '*-javadoc.jar' | sort)
if [[ ${#javadoc_jars[@]} -eq 0 ]]; then
  echo "no *-javadoc.jar under net/ - refusing to publish an empty site" >&2
  exit 1
fi

declare -A artifact_group=() artifact_dir_of=() artifact_latest=() artifact_adds=()
adds_dir="$(mktemp -d)"
trap 'rm -rf "$adds_dir"' EXIT

for jar in "${javadoc_jars[@]}"; do
  # net/<group...>/<artifactId>/<version>/<anything>-javadoc.jar. The coordinates come from the
  # directory layout, never from the file name, so a mis-named jar cannot land somewhere
  # unexpected and a changed classifier scheme cannot silently move the URLs.
  version_dir="$(dirname "$jar")"
  artifact_dir="$(dirname "$version_dir")"
  group_dir="$(dirname "$artifact_dir")"
  version="$(basename "$version_dir")"
  artifact_id="$(basename "$artifact_dir")"
  group_id="${group_dir//\//.}"

  [[ $version     =~ $SAFE ]] || { echo "refusing suspicious version '$version' ($jar)" >&2; exit 1; }
  [[ $artifact_id =~ $SAFE ]] || { echo "refusing suspicious artifactId '$artifact_id' ($jar)" >&2; exit 1; }

  # /<artifactId>/ is the site's namespace, so two groupIds publishing the same artifactId would
  # silently overwrite each other. Fail loudly instead; the fix, the day that actually happens,
  # is to key the site on <groupId>/<artifactId>.
  if [[ -n ${artifact_group[$artifact_id]:-} && ${artifact_group[$artifact_id]} != "$group_id" ]]; then
    echo "artifactId '$artifact_id' published under both ${artifact_group[$artifact_id]} and $group_id" >&2
    exit 1
  fi
  artifact_group[$artifact_id]="$group_id"
  artifact_dir_of[$artifact_id]="$artifact_dir"

  # Info-ZIP unzip already strips a leading / and ../ components, but these jars are the only
  # thing on the site produced outside this repository's own tree - check the entry names up
  # front rather than hoping someone reads a skipped-path warning out of the log.
  if unzip -Z1 "$jar" | grep -qE '(^|/)\.\.(/|$)|^/'; then
    echo "$jar contains a path traversal entry" >&2
    exit 1
  fi

  dest="$SITE_DIR/$artifact_id/$version"
  mkdir -p "$dest"
  unzip -q -o "$jar" -d "$dest"
  rm -rf "$dest/META-INF"   # a 25-byte MANIFEST.MF has no business being served
  echo "unpacked $group_id:$artifact_id:$version -> /$artifact_id/$version/"
done

for artifact_id in "${!artifact_group[@]}"; do
  metadata="${artifact_dir_of[$artifact_id]}/maven-metadata.xml"
  latest=""
  if [[ -f $metadata ]]; then
    # Maven's own answer to "which version is current": prefer the newest release, then fall back
    # to <latest>, which is what a SNAPSHOT-only artifact like beltariaspigot-api has.
    latest="$(sed -n 's:.*<release>\(.*\)</release>.*:\1:p' "$metadata" | tail -n1)"
    [[ -n $latest ]] || latest="$(sed -n 's:.*<latest>\(.*\)</latest>.*:\1:p' "$metadata" | tail -n1)"
  fi
  # Metadata absent, unparseable, or naming a version that shipped no javadoc: fall back to the
  # highest version directory that was actually unpacked.
  if [[ -z $latest || ! -d "$SITE_DIR/$artifact_id/$latest" ]]; then
    latest="$(find "$SITE_DIR/$artifact_id" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -V | tail -n1)"
  fi
  artifact_latest[$artifact_id]="$latest"

  # A real copy, not a redirect. /latest/ has to answer deep links such as
  # .../latest/net/beltaria/api/Foo.html so READMEs, IDE "external javadoc" settings and
  # `javadoc -link` can point at a URL that survives the next version bump. A meta-refresh
  # index.html would redirect the landing page only and 404 everything underneath it.
  cp -a "$SITE_DIR/$artifact_id/$latest" "$SITE_DIR/$artifact_id/latest"
  echo "$artifact_id: latest -> $latest"

  # The sources jar carries the // BeltariaSpigot markers the jar itself cannot, so the list of
  # what this fork adds is derived from the artifact rather than maintained by hand. Absent
  # sources jar, or an artifact with no markers, simply produces no section.
  sources_jar="$(find "${artifact_dir_of[$artifact_id]}/$latest" -maxdepth 1 -type f                       -name '*-sources.jar' | sort | head -n1)"
  if [[ -n $sources_jar ]]; then
    artifact_adds[$artifact_id]="$adds_dir/$artifact_id.html"
    python3 "$(dirname "${BASH_SOURCE[0]}")/api_additions.py"       "$sources_jar" "$SITE_DIR/$artifact_id/$latest" "./$artifact_id/latest"       > "${artifact_adds[$artifact_id]}"
    if [[ -s ${artifact_adds[$artifact_id]} ]]; then
      echo "$artifact_id: $(grep -c "<li>" "${artifact_adds[$artifact_id]}") documented additions"
    fi
  fi
done

{
  cat <<'HTML'
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Beltaria Maven - Javadoc</title>
<style>
  body { font: 16px/1.55 -apple-system, "Segoe UI", Roboto, sans-serif; max-width: 46rem;
         margin: 3rem auto; padding: 0 1.25rem; color: #1f2328; }
  h1 { font-size: 1.5rem; margin-bottom: .25rem; }
  h2 { font-size: 1.05rem; margin: 2rem 0 .25rem; font-family: ui-monospace, SFMono-Regular, monospace; }
  h3 { font-size: .98rem; margin: 1.5rem 0 .2rem; font-weight: 600; }
  h3 code { background: none; padding: 0; }
  p.sub { color: #59636e; margin-top: 0; font-size: .92rem; }
  code { background: #f6f8fa; border-radius: 4px; padding: .1em .35em; font-size: .9em; }
  ul { padding-left: 1.2rem; } li { margin: .15rem 0; }
  a { color: #0969da; text-decoration: none; } a:hover { text-decoration: underline; }
  @media (prefers-color-scheme: dark) {
    body { background: #0d1117; color: #e6edf3; }
    p.sub { color: #9198a1; } code { background: #161b22; } a { color: #4493f8; }
  }
</style>
</head>
<body>
<h1>Beltaria Maven &mdash; Javadoc</h1>
<p class="sub">API documentation unpacked from the <code>-javadoc.jar</code> artifacts in
<a href="https://github.com/Beltaria/beltariaspigot">Beltaria/beltariaspigot</a>, rebuilt on every publish.
The jars themselves are still resolved from
<code>https://raw.githubusercontent.com/Beltaria/beltariaspigot/main/</code>.</p>
HTML

  for artifact_id in $(printf '%s\n' "${!artifact_group[@]}" | sort); do
    printf '<h2>%s:%s</h2>\n<ul>\n' "${artifact_group[$artifact_id]}" "$artifact_id"
    printf '<li><a href="./%s/latest/"><strong>latest</strong></a> &mdash; currently %s</li>\n' \
      "$artifact_id" "${artifact_latest[$artifact_id]}"
    while read -r version; do
      printf '<li><a href="./%s/%s/">%s</a></li>\n' "$artifact_id" "$version" "$version"
    done < <(find "$SITE_DIR/$artifact_id" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' \
             | grep -vx latest | sort -Vr)
    printf '</ul>\n'
    if [[ -s ${artifact_adds[$artifact_id]:-} ]]; then
      cat "${artifact_adds[$artifact_id]}"
    fi
  done

  printf '<p class="sub">Generated %s from %s.</p>\n</body>\n</html>\n' \
    "$(date -u '+%Y-%m-%d %H:%M UTC')" "${GITHUB_SHA:-local}"
} > "$SITE_DIR/index.html"

du -sh "$SITE_DIR"
