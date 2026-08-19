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

Downstream javadoc builds can cross-link into it:

```
javadoc -link https://beltaria.github.io/maven/beltariaspigot-api/latest/
```

The site is built by the **Publish Javadoc** workflow and deployed straight from the Actions
artifact — no HTML is ever committed to this repository, and the Maven tree consumed over
`raw.githubusercontent.com` is untouched.

## Publishing (automated)

Do not commit artifacts here by hand. The **Publish API** workflow in the private
BeltariaSpigot repository builds `beltariaspigot-api` and pushes it here whenever an
API-affecting change lands on `master` (API patches, upstream bump, build logic), or on
manual dispatch. It authenticates with a deploy key scoped to this repository only
(`MAVEN_DEPLOY_KEY` secret in BeltariaSpigot).

That deploy-key push is also what triggers the **Publish Javadoc** workflow here: pushes
authenticated with `GITHUB_TOKEN` do not start workflow runs, so keep the deploy key — swapping
it for a token would silently stop the docs from rebuilding.
