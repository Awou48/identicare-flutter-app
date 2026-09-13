package com.example.identicare_mobile

import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyInfo
import android.security.keystore.KeyPermanentlyInvalidatedException
import android.security.keystore.KeyProperties
import android.util.Base64
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.security.KeyFactory
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.PrivateKey
import java.security.Signature
import java.security.spec.ECGenParameterSpec

class KeystoreSigner(private val activity: FragmentActivity) : MethodChannel.MethodCallHandler {

    companion object {
        const val CHANNEL = "identicare/keystore"
        private const val PROVIDER = "AndroidKeyStore"
    }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        try {
            when (call.method) {
                "hasKey" -> result.success(hasKey(call.argument<String>("alias")!!))
                "getKey" -> result.success(describeKey(call.argument<String>("alias")!!))
                "generateKey" -> result.success(
                    generateKey(
                        call.argument<String>("alias")!!,
                        Base64.decode(call.argument<String>("challengeB64")!!, Base64.NO_WRAP),
                    )
                )
                "deleteKey" -> {
                    keyStore().deleteEntry(call.argument<String>("alias")!!)
                    result.success(true)
                }
                "sign" -> sign(
                    call.argument<String>("alias")!!,
                    call.argument<String>("payload")!!,
                    call.argument<String>("title") ?: "Verifikasi Sidik Jari",
                    call.argument<String>("subtitle") ?: "",
                    call.argument<String>("negativeButton") ?: "Batal",
                    result,
                )
                else -> result.notImplemented()
            }
        } catch (e: KeyPermanentlyInvalidatedException) {

            result.error("KEY_INVALIDATED", e.message, null)
        } catch (e: IllegalStateException) {

            result.error("NO_BIOMETRICS", e.message, null)
        } catch (e: Exception) {
            result.error("ERROR", "${e.javaClass.simpleName}: ${e.message}", null)
        }
    }

    private fun keyStore(): KeyStore = KeyStore.getInstance(PROVIDER).apply { load(null) }

    private fun hasKey(alias: String): Boolean = keyStore().containsAlias(alias)

    private fun generateKey(alias: String, challenge: ByteArray): Map<String, Any?> {
        val builder = KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_SIGN)
            .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
            .setDigests(KeyProperties.DIGEST_SHA256)
            .setUserAuthenticationRequired(true)

            .setInvalidatedByBiometricEnrollment(true)

            .setAttestationChallenge(challenge)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {

            builder.setUserAuthenticationParameters(0, KeyProperties.AUTH_BIOMETRIC_STRONG)
        } else {
            @Suppress("DEPRECATION")
            builder.setUserAuthenticationValidityDurationSeconds(-1)
        }

        val generator = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, PROVIDER)
        generator.initialize(builder.build())
        val pair = generator.generateKeyPair()

        return describeKey(alias)
            ?: throw IllegalStateException("key $alias vanished right after generation")
    }

    private fun describeKey(alias: String): Map<String, Any?>? {
        val ks = keyStore()
        val entry = ks.getEntry(alias, null) as? KeyStore.PrivateKeyEntry ?: return null
        val chain = ks.getCertificateChain(alias)?.map {
            Base64.encodeToString(it.encoded, Base64.NO_WRAP)
        } ?: emptyList()
        return mapOf(

            "publicKeyDerB64" to Base64.encodeToString(entry.certificate.publicKey.encoded, Base64.NO_WRAP),
            "attestationChainB64" to chain,
            "securityLevel" to securityLevel(entry.privateKey),
        )
    }

    private fun securityLevel(key: PrivateKey): String {
        return try {
            val factory = KeyFactory.getInstance(key.algorithm, PROVIDER)
            val info = factory.getKeySpec(key, KeyInfo::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                when (info.securityLevel) {
                    KeyProperties.SECURITY_LEVEL_STRONGBOX -> "STRONGBOX"
                    KeyProperties.SECURITY_LEVEL_TRUSTED_ENVIRONMENT -> "TEE"
                    KeyProperties.SECURITY_LEVEL_SOFTWARE -> "SOFTWARE"
                    else -> "UNKNOWN"
                }
            } else {
                @Suppress("DEPRECATION")
                if (info.isInsideSecureHardware) "TEE" else "SOFTWARE"
            }
        } catch (e: Exception) {
            "UNKNOWN"
        }
    }

    private fun sign(
        alias: String,
        payload: String,
        title: String,
        subtitle: String,
        negativeButton: String,
        result: MethodChannel.Result,
    ) {
        val entry = keyStore().getEntry(alias, null) as? KeyStore.PrivateKeyEntry
            ?: return result.error("NO_KEY", "no key under alias $alias", null)

        val canAuth = BiometricManager.from(activity)
            .canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_STRONG)
        when (canAuth) {
            BiometricManager.BIOMETRIC_SUCCESS -> Unit
            BiometricManager.BIOMETRIC_ERROR_NONE_ENROLLED ->
                return result.error("NO_BIOMETRICS", "no strong biometric enrolled", null)
            else -> return result.error("HW_UNAVAILABLE", "canAuthenticate=$canAuth", null)
        }

        val signature = Signature.getInstance("SHA256withECDSA")
        signature.initSign(entry.privateKey)

        val promptInfo = BiometricPrompt.PromptInfo.Builder()
            .setTitle(title)
            .setSubtitle(subtitle)
            .setNegativeButtonText(negativeButton)
            .setAllowedAuthenticators(BiometricManager.Authenticators.BIOMETRIC_STRONG)
            .setConfirmationRequired(false)
            .build()

        var answered = false
        fun reply(block: () -> Unit) {
            if (!answered) {
                answered = true
                block()
            }
        }

        val callback = object : BiometricPrompt.AuthenticationCallback() {
            override fun onAuthenticationSucceeded(res: BiometricPrompt.AuthenticationResult) {
                try {

                    val sig = res.cryptoObject?.signature
                        ?: return reply { result.error("ERROR", "no crypto object", null) }
                    sig.update(payload.toByteArray(Charsets.UTF_8))
                    val der = sig.sign()
                    reply { result.success(mapOf("signatureB64" to Base64.encodeToString(der, Base64.NO_WRAP))) }
                } catch (e: Exception) {
                    reply { result.error("ERROR", "${e.javaClass.simpleName}: ${e.message}", null) }
                }
            }

            override fun onAuthenticationError(code: Int, msg: CharSequence) {
                val mapped = when (code) {
                    BiometricPrompt.ERROR_NEGATIVE_BUTTON,
                    BiometricPrompt.ERROR_USER_CANCELED,
                    BiometricPrompt.ERROR_CANCELED -> "USER_CANCELLED"
                    BiometricPrompt.ERROR_LOCKOUT,
                    BiometricPrompt.ERROR_LOCKOUT_PERMANENT -> "LOCKED_OUT"
                    BiometricPrompt.ERROR_NO_BIOMETRICS -> "NO_BIOMETRICS"
                    BiometricPrompt.ERROR_HW_UNAVAILABLE,
                    BiometricPrompt.ERROR_HW_NOT_PRESENT -> "HW_UNAVAILABLE"
                    BiometricPrompt.ERROR_TIMEOUT -> "TIMEOUT"
                    else -> "ERROR"
                }
                reply { result.error(mapped, "$code: $msg", null) }
            }

            override fun onAuthenticationFailed() {

            }
        }

        activity.runOnUiThread {
            try {
                BiometricPrompt(activity, ContextCompat.getMainExecutor(activity), callback)
                    .authenticate(promptInfo, BiometricPrompt.CryptoObject(signature))
            } catch (e: Exception) {
                reply { result.error("ERROR", "${e.javaClass.simpleName}: ${e.message}", null) }
            }
        }
    }
}
