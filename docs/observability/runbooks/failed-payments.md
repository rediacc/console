# Debugging Failed Payments and Webhooks

This guide covers how to investigate payment failures end-to-end. The payment flow has several stages, and failures can be silent — the webhook returns 200 but a side effect (email, token revocation, subscription update) quietly fails.

## How the payment flow works

```
User pays via Stripe
  -> Stripe sends webhook POST to /account/api/v1/webhooks/stripe
    -> processEvent() routes the event to a handler
      -> Handler performs side effects:
           - Send email (welcome, cancellation, payment failed)
           - Create/revoke API tokens
           - Update subscription status in database
           - Update Stripe metadata
```

Any step in this chain can fail. The webhook endpoint itself might return 5xx (step fails loudly) or it might return 200 while a side effect fails silently (step fails quietly). Both scenarios need different investigation paths.

## Steps

### 1. Open the Error Observatory

Go to the [Error Observatory](https://grafana.rediacc.io/d/error-observatory) dashboard.

### 2. Check for webhook endpoint errors

In the "Error Rate by Route" panel, look for `/webhooks/stripe` or `POST /account/api/v1/webhooks/stripe`. If this route has an elevated error rate, the webhook endpoint itself is failing — Stripe will retry these.

### 3. Investigate 5xx webhook errors

If the webhook endpoint is returning 5xx errors:

1. Click a trace in the "Recent Error Traces" panel that corresponds to the webhook route
2. In the trace detail, check the error attributes (`error.type`, `error.message`, `error.stack`)
3. Common causes of 5xx webhook errors:
   - **Stripe signature verification failure** — the `STRIPE_WEBHOOK_SECRET` environment variable is wrong or the request body was modified in transit. Check `error.code = STRIPE_WEBHOOK_SIGNATURE_INVALID`.
   - **Database error** — the subscription or user record could not be updated. Check for `DatabaseError` in `error.type`.
   - **Invalid event schema** — Stripe sent an event type the handler does not recognize, or the event payload is missing expected fields.

### 4. Investigate silent side-effect failures

If the webhook endpoint is returning 200 (no errors in the Error Observatory) but something downstream did not happen (user did not get an email, subscription status is stale, token was not revoked):

1. Go to **Grafana Explore** (compass icon in the left sidebar)
2. Select the **Tempo** datasource
3. Search with:
   - **Service Name** = `rediacc-account-server`
   - **Span Name** containing `webhooks` (or the specific route)
   - Set the time range to when the payment was made
4. Click a matching trace to open the waterfall view
5. Expand the root span and look for **span events** named `non_critical_error`
6. These events have attributes that tell you exactly what failed

### 5. Read the error context

The `error.context` attribute on `non_critical_error` events tells you which side effect failed:

| `error.context` value | What failed | Impact |
|----------------------|-------------|--------|
| `webhook.email` | Transactional email was not sent (welcome, cancellation, or payment-failed email) | User does not receive email notification. No data loss. |
| `webhook.token_revoke` | API token revocation failed after a subscription change | User's old tokens may still work after downgrade/cancellation. Security concern. |
| `webhook.event_log` | Event logging to the database failed | Gap in audit trail. The payment itself succeeded. |
| `webhook.stripe_metadata` | Stripe metadata update failed | Stripe dashboard may show stale metadata. No functional impact. |
| `billing.cancel_subscription` | Stripe subscription cancellation API call failed | The subscription may still be active on Stripe's side. Requires manual cancellation. |
| `billing.token_revoke` | Token revocation during a refund failed | Similar to `webhook.token_revoke` — old tokens may still work. |

### 6. Check email delivery in Loki

If the issue is specifically about emails not being delivered, search the logs:

1. Go to **Grafana Explore** → select **Loki** datasource
2. Run this LogQL query:

```logql
{source="docker"} |~ "email.delivery"
```

The `recordNonCriticalError` utility logs the SES response status, so you will see whether the email API call failed (SES rejected it) or was never attempted (error happened before the send call).

### 7. Cross-reference with Stripe's dashboard

Go to [Stripe Dashboard](https://dashboard.stripe.com) → Developers → Webhooks → Recent Events.

Find the event in question and check:

- **Delivery status**: Did Stripe successfully deliver the webhook?
- **Response code**: What HTTP status did your endpoint return?
- **Response body**: If your endpoint returned an error, Stripe logs the response body.

If Stripe shows the webhook was delivered and your endpoint returned 200, the problem is in side effects (steps 4-5 above). If Stripe shows delivery failed, the problem is in the endpoint itself (step 3).

### 8. Trace back to code

The key code path for webhook processing:

```
private/account/src/services/webhook.service.ts
  -> processEvent()        # Routes Stripe event to the correct handler
  -> handleCheckoutCompleted()      # New subscription created
  -> handleSubscriptionUpdated()    # Plan change, renewal, trial end
  -> handleSubscriptionDeleted()    # Cancellation
  -> handleInvoicePaymentFailed()   # Payment failure
```

Each handler follows the same pattern: perform the critical database update first (this is the part that causes a 5xx if it fails), then fire off side effects wrapped in `recordNonCriticalError()` so they fail silently.
