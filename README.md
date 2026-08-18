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

## Publishing (maintainers)

From this repository's checkout, with the BeltariaSpigot working copy as a sibling of
the `1.8.8` folder layout:

```powershell
.\publish-api.ps1
```

The script runs `:beltariaspigot-api:publishToMavenLocal` in the BeltariaSpigot
checkout, copies the `net/beltaria` tree from `~/.m2/repository` into this repo,
renames `maven-metadata-local.xml` to `maven-metadata.xml`, and commits + pushes.
