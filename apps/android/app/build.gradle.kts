// Provok for Android: a Trusted Web Activity. The app opens the website full-screen in Chrome (no URL bar), so every
// web feature (sign-in, debates, video, payments) works and web deploys reach the app without a Play release.
// Digital Asset Links tie the two together: the site serves /.well-known/assetlinks.json (ANDROID_PACKAGE and
// ANDROID_CERT_SHA256 in the server env) and the app declares the site in @string/asset_statements.
import java.util.Properties

plugins {
    id("com.android.application")
}

// Upload-key signing. Locally from keystore.properties (gitignored, see README); in CI from environment variables.
val keystoreProps = Properties().apply {
    val f = rootProject.file("keystore.properties")
    if (f.exists()) f.inputStream().use { load(it) }
}
fun secret(key: String, env: String): String? = keystoreProps.getProperty(key) ?: System.getenv(env)

// One build per environment: the host is the only thing that differs.
val environments = mapOf(
    "staging" to "staging.provok.in",
    "production" to "provok.in",
)

android {
    namespace = "com.provok.twa"
    compileSdk = 37

    defaultConfig {
        applicationId = "in.provok.app"
        minSdk = 24
        targetSdk = 36
        // Bump for every Play upload (Play rejects a versionCode it has seen). Override with -PversionCode=N.
        versionCode = (project.findProperty("versionCode") as String?)?.toInt() ?: 1
        versionName = (project.findProperty("versionName") as String?) ?: "1.0.0"
    }

    buildFeatures {
        resValues = true
    }

    signingConfigs {
        create("upload") {
            secret("storeFile", "ANDROID_KEYSTORE_FILE")?.let { storeFile = file(it) }
            storePassword = secret("storePassword", "ANDROID_KEYSTORE_PASSWORD")
            keyAlias = secret("keyAlias", "ANDROID_KEY_ALIAS")
            keyPassword = secret("keyPassword", "ANDROID_KEY_PASSWORD")
        }
    }

    flavorDimensions += "env"
    productFlavors {
        environments.forEach { (env, host) ->
            create(env) {
                dimension = "env"
                if (env != "production") {
                    applicationIdSuffix = ".$env"
                    versionNameSuffix = "-$env"
                }
                manifestPlaceholders["hostName"] = host
                resValue("string", "app_name", if (env == "production") "Provok" else "Provok ${env.replaceFirstChar { it.uppercase() }}")
                resValue("string", "launch_url", "https://$host/")
                // Android string resources drop bare double quotes, so escape them or the JSON is unreadable.
                val statements = """[{"relation":["delegate_permission/common.handle_all_urls"],"target":{"namespace":"web","site":"https://$host"}}]"""
                resValue("string", "asset_statements", statements.replace("\"", "\\\""))
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("upload").takeIf { it.storeFile != null }
        }
    }
}

dependencies {
    implementation("com.google.androidbrowserhelper:androidbrowserhelper:2.7.4")
}
