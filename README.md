# Beltaria Maven repository

Public Maven artifacts for the Beltaria server ecosystem, served straight from this
repository. Currently hosts **`net.beltaria:beltariaspigot-api`** (the BeltariaSpigot
plugin API — the server itself stays private; the API is just interfaces).

## Consuming

Gradle (Kotlin DSL):

```kotlin
repositories {
    maven("https://raw.githubusercontent.com/Beltaria/maven/main/") {
        content { includeGroup("net.beltaria") }
    }
}

dependencies {
    compileOnly("net.beltaria:beltariaspigot-api:1.8.8-R0.1-SNAPSHOT")
}
```

Note: raw.githubusercontent.com is CDN-cached for ~5 minutes; freshly published
artifacts can take that long to appear.

## Javadoc

Browsable API docs, unpacked from the published `-javadoc.jar` on every publish:
**<https://beltaria.github.io/maven/beltariaspigot-api/latest/>**

`/latest/` is a stable alias for the current version and is safe to deep-link; the exact
version is also served at `/beltariaspigot-api/1.8.8-R0.1-SNAPSHOT/`. The index at
<https://beltaria.github.io/maven/> lists everything available.

That index also carries a **What BeltariaSpigot adds** section: every API addition this
fork makes on top of PandaSpigot, deep-linked into the javadoc. It is generated from the
`// BeltariaSpigot` markers in the published sources jar, so it cannot drift from the
artifact it documents - keep wrapping API patches in those markers and new additions show
up on their own.

Downstream javadoc builds can cross-link into it:

```
javadoc -link https://beltaria.github.io/maven/beltariaspigot-api/latest/
```

The site is built by the **Publish Javadoc** workflow and deployed straight from the Actions
artifact — no HTML is ever committed to this repository, and the Maven tree consumed over
`raw.githubusercontent.com` is untouched.

## Server configuration

The full `pandaspigot.yml` reference — all 146 options with their types, defaults and
descriptions — is in this repository's wiki:
**<https://github.com/Beltaria/maven/wiki/Configuration>**

Options are split by scope: [global](https://github.com/Beltaria/maven/wiki/Configuration-Global)
settings, and [per-world](https://github.com/Beltaria/maven/wiki/Configuration-Per-World) ones
with a page each for the larger sections. The index also lists the handful of defaults that
deviate from vanilla.

Like the javadoc, it is generated — from the Configurate `@Comment` annotations on the server's
config classes, by the **Publish Wiki** workflow in BeltariaSpigot — so it says exactly what the
file the server writes says. Do not edit the wiki pages by hand; they are replaced on the next
publish. Change the `@Comment` on the field instead.

## Publishing (automated)

Do not commit artifacts here by hand. The **Publish API** workflow in the private
BeltariaSpigot repository builds `beltariaspigot-api` and pushes it here whenever an
API-affecting change lands on `master` (API patches, upstream bump, build logic), or on
manual dispatch. It authenticates with a deploy key scoped to this repository only
(`MAVEN_DEPLOY_KEY` secret in BeltariaSpigot).

That deploy-key push is also what triggers the **Publish Javadoc** workflow here: pushes
authenticated with `GITHUB_TOKEN` do not start workflow runs, so keep the deploy key — swapping
it for a token would silently stop the docs from rebuilding.
