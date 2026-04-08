# TOOLS.md - Local Notes

### Flight Search
- Provider: Amadeus Self-Service API (api.amadeus.com)
- Auth: AMADEUS_API_KEY stored in config.json
- Rate limit: 10 calls/sec, 500/day on free tier
- Use v2 flight-offers-search endpoint

### Hotels
- Same Amadeus key for hotel-search v3 endpoint
- Always query with Marriott Bonvoy loyalty program filter

### Seat Selection
- No API access — check airline site manually after booking
- United: united.com/manageres/mytrips
- ANA: ana.co.jp/en/us/book-plan/manage
