# Market Data Details

Live market data is now fetched from the Binance USD-M Futures Testnet via the
`POST /paper-sessions/binance-testnet/market-data/sync` API endpoint and stored
locally in `backend/agent/paper_sessions/market_data/`.

The manually copied Binance reference documents were removed from this directory.
To keep data fresh, schedule a cron job or frontend task to call the sync
endpoint daily.
