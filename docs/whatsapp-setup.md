# WhatsApp approvals setup (one time, about 20 minutes)

Bob texts you from your WhatsApp Business number through Meta's official Cloud API. Your Yes/No taps go to a small Supabase function, and the Mac picks them up from there.

## 1. Meta app and business number
1. Go to developers.facebook.com → My Apps → Create app → type **Business** → add the **WhatsApp** product.
2. WhatsApp → API Setup → **Add phone number** and choose your existing WhatsApp Business number. Pick the option to keep using it in the WhatsApp Business app ("coexistence"), and scan the QR code from the Business app when asked.
3. Note the **Phone number ID** (not the phone number itself).
4. Business Settings → System users → add a system user with **Admin** role → Generate token for the app with `whatsapp_business_messaging` and `whatsapp_business_management`. This is a permanent token.
5. Add a payment method in WhatsApp Manager (Meta stops delivering after the free tier without one; expected cost is under $1/month).

## 2. Message templates (needed when you haven't messaged Bob in 24 hours)
In WhatsApp Manager → Message templates, create two **Utility** templates in English:
- `research_approval`: body `{{1}}`, buttons: two **Quick reply** buttons, "Yes" and "No".
- `research_update`: body `{{1}}`, no buttons.
Approval usually takes minutes.

Tip: sending Bob any message once a day keeps the free 24-hour window open.

## 3. Webhook
Supabase function URL: `https://<project-ref>.supabase.co/functions/v1/wa-webhook`
1. Pick a random verify token and relay secret: `openssl rand -hex 16` (twice).
2. Set function secrets (Supabase dashboard → Edge Functions → Secrets): `WA_VERIFY_TOKEN`, `WA_APP_SECRET` (Meta app → Settings → Basic → App secret), `RELAY_SECRET`.
3. Meta app → WhatsApp → Configuration → Webhook: callback URL above, verify token from step 1 → Verify and save → subscribe to the **messages** field.

## 4. Keychain on the Mac
```bash
security add-generic-password -s research-council -a wa_token -w '<system user token>'
security add-generic-password -s research-council -a wa_phone_id -w '<phone number id>'
security add-generic-password -s research-council -a wa_to -w '<your personal WhatsApp number, digits only, with country code>'
security add-generic-password -s research-council -a relay_url -w 'https://<project-ref>.supabase.co/functions/v1/wa-webhook'
security add-generic-password -s research-council -a relay_secret -w '<relay secret>'
```

## 5. Test
`uv run python -m research_council.approvals --test` → tap **Yes** on your phone → it prints `yes`.
