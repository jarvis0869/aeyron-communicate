# Launch readiness

## Ready for a technical preview

- [x] Typed capture and approval flow
- [x] Local notebook with delete and export
- [x] ParkiBot handoff that sends no user payload
- [x] Backend health/config/session/rewrite endpoints
- [x] Speech disabled safely until provider configuration is complete
- [x] Request limits, idempotency, cleanup, and content-free errors
- [x] Frontend unit tests and backend safety/lifecycle tests
- [x] Production build

## Before enabling speech for real users

- [ ] Configure a provider account, data-processing terms, retention, and regional routing
- [ ] Set `AEYRON_TRANSCRIPTION_ENABLED=true` and `AEYRON_PROVIDER_PRIVACY_ACKNOWLEDGED=true` only after review
- [ ] Use HTTPS and production CORS origins
- [ ] Add secret management and operational monitoring that excludes content
- [ ] Test microphones, codecs, network transitions, and deletion on target devices
- [ ] Publish accessible consent and a plain-language privacy notice
- [ ] Add a data-subject request process if required by the deployment jurisdiction

## Before any health or Parkinson's claim

- [ ] Define the intended claim and a preregistered validation protocol
- [ ] Obtain ethics review and participant consent
- [ ] Use representative, consented speech data with environmental metadata
- [ ] Report sensitivity, specificity, calibration, missingness, and subgroup performance
- [ ] Keep communication assistance separate from diagnosis and treatment
- [ ] Establish clinical oversight and an incident response path

The current repository is suitable for a technical preview, not a medical device claim.
