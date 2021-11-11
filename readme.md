# DESC

Very simple script that allows dollar cost averaging a bag of currencies using
the Gemini api.

Besides saving time, this is particularly important for Gemini where fees scale
inversely with purchase size, ranging from 10%-1.49%. Using the API, you pay a
flat 0.350% invariant of order size.

The script also handles the logging of important trade data like cost, amount,
fee, time cost basis, etc. to the dir in which the python interpreter is run.

# TODO

- Write a sell function.
- "wash sale" function (tax deduction).
- interactivity beyond. 1. run it 2. y-or-n-p for each pair in bag 3. done
- refactor, especially some of the configuration vars
