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

## Publishing (automated)

Do not commit artifacts here by hand. The **Publish API** workflow in the private
BeltariaSpigot repository builds `beltariaspigot-api` and pushes it here whenever an
API-affecting change lands on `master` (API patches, upstream bump, build logic), or on
manual dispatch. It authenticates with a deploy key scoped to this repository only
(`MAVEN_DEPLOY_KEY` secret in BeltariaSpigot).
