import crypto from "crypto";

/**
 * Verify a GitHub webhook signature (X-Hub-Signature-256 header).
 *
 * GitHub computes: sha256=HMAC(secret, rawBody)
 * We recompute the same HMAC and compare using timingSafeEqual to prevent
 * timing-based attacks on the comparison.
 *
 * @param secret   The GITHUB_WEBHOOK_SECRET configured in the GitHub App / repo webhook settings.
 * @param payload  The raw request body as a Buffer (must be the original bytes, pre-JSON-parse).
 * @param signature The value of the X-Hub-Signature-256 header, e.g. "sha256=abc123...".
 * @returns true if the signature is valid, false otherwise.
 */
export function verifyGithubSignature(
    secret: string,
    payload: Buffer,
    signature: string,
): boolean {
    const expected = `sha256=${crypto
        .createHmac("sha256", secret)
        .update(payload)
        .digest("hex")}`;

    try {
        // Both buffers must be the same length for timingSafeEqual
        return (
            expected.length === signature.length &&
            crypto.timingSafeEqual(
                Buffer.from(expected, "utf8"),
                Buffer.from(signature, "utf8"),
            )
        );
    } catch {
        return false;
    }
}
