# Trip statistics: collecting, checking, showing

How the numbers for an EV road-trip film are gathered and shown: charge captions, route legs, the
summary card, the conclusion. Worked out on the Helm film (Tesla Model 3, 1255 km in a day, five
fast chargers, two review rounds on the numbers alone). Every rule here exists because a number
on screen was wrong or disputed once.

## 1. Sources, and which one wins

| what | source | notes |
|---|---|---|
| trip total: km, driving time, Wh/km, kWh | car screen at the end (trip card filmed in the last clip) | the one the viewer can see on screen |
| per drive: start, end, % at both ends, km, kWh | logger (TeslaFi, TeslaMate) screenshots from the user | start time from the logger |
| per charge: start, end, % at both ends, kWh added, kW | logger | "added" is what reached the battery |
| what each charge cost, kWh billed | charger app / receipt / bank, one line per **payment** | billed kWh > added kWh (losses); cost uses billed |
| trip finish time | the video: file time of the last clip plus what is said ("ми доїхали") | the logger can end the drive late while the car stays in D |
| home charging cost | logger kWh from the wall x tariff from the user's invoice | energy + variable network fees + VAT; fixed monthly fees left out unless asked |
| fuel comparison | the user's own consumption figures x the fuel price on that date (named source) | a range, not one number |

- **The user's memory is a hypothesis, not a source.** Check it against the logger and against any
  screen visible in the footage (car screen with the clock and %). Helm: the user remembered arriving
  at 4 %; the logger said 7.49 % and the car screen at 12:48 showed 8 %. Report the evidence, use 7 %.
- **An interrupted charge is two sessions and two payments.** When the logger shows two charges at
  one place, ask the user to check the charger app for the second payment; it is easy to forget and
  it changes the trip total (Helm: 87 PLN missing from the first count).
- **Footage beats logger for times the logger cannot know** (end of trip with the car in D, waiting
  with the car parked in Sentry). Logger beats footage for times nobody filmed.

## 2. trip_stats.md in the project

One file holds every number and where it came from, before anything goes on screen:

- a sources line per figure (screenshot date, app, invoice number, URL for prices);
- one line per drive and per charge, in time order: times, minutes, % from -> to, km, kWh, Wh/km, avg/max speed;
- sums with the formula written out (sessions added up, home kWh x tariff, cost per 100 km);
- a "review N" section for every correction the user made, with the evidence that settled it;
- a line saying **never show the logger screenshots**: their map shows the home address. Numbers only.

## 3. On screen

**Charge caption** (two captions in a row, burnt into the talk clip with `burn_in.py`):

1. Title: `network place · arrive–depart` = the **whole stop**, from the end of the drive in to the start
   of the drive out (plugging in, paying and unplugging always cost a few minutes; the user wants that seen).
   Sub: `N хв стоянки (M зарядки) · a → b % · kWh billed · PLN (PLN/kWh)`.
2. What the stop was used for, in the user's words (lunch, toilet, washing the windscreen, waiting for a
   train). Ask the user; it answers "you sat half an hour in the car". A fault goes here too: the sessions
   with their times and what it cost (Helm: "тому лише 82 %, а не 90+ за ABRP").

Measure each line in the caption font before burning: title 60 px, sub 46 px, keep it under ~1800 px
of 1920 (PIL `ImageFont.truetype(vf.FONT_BOLD, 46).getlength(text)`). Shorten by moving the price per
kWh into brackets, not by dropping the stop time.

**Route legs** (`example_make_route.py`): each leg panel gets the logger times (leg k ends at the arrival
at charger k, leg k+1 starts at the departure) and a line `батарея a % → b %`. The km come from the map
line, which starts and ends at a public place, not at home, so the first and last legs are shorter than
the logger's; say so to the user rather than mixing the two.

**Summary card**: total km, driving time, average moving speed = km / driving time, door to door,
Wh/km, fast charges (kWh, cost), home charge, total, cost per 100 km, the fuel comparison. Ukrainian
number style: decimal comma, `·` between items, en dash in time ranges.

## 4. Conclusion (pinned comment, description), not the film

Collect in the project's release notes as the review goes: stop minutes vs charging minutes per
charger, price per kWh per network, faults per network, what changed in the networks since the last
trip. Helm: Superchargers 1.50-1.70 PLN/kWh, GreenWay 2.40, Ionity 2.05 and the only fault of the
trip; the user also counts how much the Supercharger network has improved as a big plus.

## 5. Reporting to the user

- A table: each figure, its value, its source. Mark what changed since the captions now in the film.
- Ask only for what no source has: the stop activities, a payment missing from the app list, which
  memory to trust when footage and memory disagree.
- After burning: frames of every caption and every route panel, checked; then frames from the
  finished film, because filmkit may cut a caption short.
