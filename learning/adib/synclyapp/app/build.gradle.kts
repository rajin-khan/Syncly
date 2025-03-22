plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
}

android {
    namespace = "com.example.syncly"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.example.syncly"
        minSdk = 27
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

        buildConfigField("String", "DROPBOX_APP_KEY", "\"w84emdpux17qpnj\"")
        buildConfigField("String", "DROPBOX_APP_SECRET", "\"x6ce7dtmj51xqc7\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    // Add this block to resolve the duplicate file issue
    packaging {
        resources {
            excludes += "META-INF/INDEX.LIST"
            excludes += "META-INF/DEPENDENCIES"
            excludes += "META-INF/native-image/org.mongodb/bson/native-image.properties"
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_21
        targetCompatibility = JavaVersion.VERSION_21
        isCoreLibraryDesugaringEnabled = true
    }

    buildFeatures {
        compose = true
        buildConfig = true // Explicitly enable BuildConfig generation
    }
}

dependencies {
    implementation(libs.appcompat)
    implementation(libs.material)
    implementation(libs.lifecycle.runtime.ktx)
    implementation(libs.activity.compose)
    implementation(platform(libs.compose.bom))
    implementation(libs.ui)
    implementation(libs.ui.graphics)
    implementation(libs.ui.tooling.preview)
    implementation(libs.material3)
    implementation(libs.activity)
    implementation(libs.constraintlayout)
    testImplementation(libs.junit)
    androidTestImplementation(libs.ext.junit)
    androidTestImplementation(libs.espresso.core)
    androidTestImplementation(platform(libs.compose.bom))
    androidTestImplementation(libs.ui.test.junit4)
    debugImplementation(libs.ui.tooling)
    debugImplementation(libs.ui.test.manifest)
    implementation(libs.play.services.auth)
    implementation(libs.google.auth.library.oauth2.http.v1300)
    implementation(libs.google.http.client.android)
    implementation(libs.google.api.client.android.v272)
    implementation(libs.google.api.services.drive)
    implementation(libs.mongodb.driver.sync.v4101)
    //implementation (libs.mongo.java.driver)
    implementation(libs.dropbox.core.sdk) // Check for the latest version
    //implementation("com.dropbox.core:dropbox-core-sdk:5.4.3")   //Older version for .android.Auth
    //implementation(libs.dropbox.android.sdk)
    implementation(libs.slf4j.api)
    implementation(libs.slf4j.simple)
    coreLibraryDesugaring(libs.desugar.jdk.libs)
}
