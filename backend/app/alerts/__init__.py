"""Alert engine: rules persisted in SQLite, evaluated server-side on the
live quote cadence, fired events audited and pushed over the quote socket.

Semantics follow the platforms users already know (TradingView/thinkorswim):
crossing operators remember which side of the level the metric was on
(`last_state`) and fire only on an actual cross — the first evaluation
after creation/restart SEEDS the side without firing, so restarts never
cause phantom alerts. Cooldowns cap re-fires; `once` rules self-pause.

Alerts only ever notify and (optionally, later) start research — they
never place orders. The human-approval gate is untouched.
"""
