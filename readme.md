# DESC

This is a dumb script that purchases a three hundred sixty fifth (once a day) of
a constant amount of BTC using the gemini api for substantially reduced
fees. This is especially important for averaging cost over a granularity like
daily or twice a day, etc. Since the less you buy, the more you pay through
their standard interface.

Assuming you aren't purchasing more than 1e6 USD of some cryptocurrency per
month, your fees could range from 10%-1.49% (varies by order size). Using the
api, you pay a flat 0.350% invariant of order size.

It also logs important cost, amount, fee, time, cost basis, etc to the dir in
which the python interpreter is run.

Little additional functionality provided, though would be trivial to add
additional currencies. Setting weights for a currency bag would require a bit
more logic.

# TODO

Write a sell function.
