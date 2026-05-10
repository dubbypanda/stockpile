# YouTube Script: Options Scanner

## Title Ideas

### keep this one
- Option Scanner by Claude (Python, GitHub)
- 
- 
- 
- 
- Claude finds the best Options
- "Use Claude to find the Best Options (Python)"
- "Claude Code Finds Mis-Priced Options (Python)"

- "I Built a Free Web App That Finds Mispriced Options"
- "See Which Options Are Overpriced — In One Chart"
- "Click Scan → See the Best Options to Sell (Free Tool)"
- "The Options Screener Your Broker Doesn't Have"
- "Find Overpriced Options in 30 Seconds (Free, Any Ticker)"
- "I Built an Options Scanner with Claude Code — Here's How to
  Use It"

---

## HOOK (0:00–1:15)

[10 SHOW Yahoo Finance Option Chain]*

If you sell options — covered calls, cash secured puts,
you've probably stared at an option chain and wondered
which contract is actually the best one to sell.

Same goes for option buyers.

[11 Option Scanner load screen]

So I decided to build a tool to help, a free option scanner
made with Claude Code.  I built it in a few nights.  It finds the best
options from Yahoo Finance Option Chains and

(scroll to see pre populated chart and tables)

shows them to you in a chart and 2 tables.

Let me demonstrate:

Let's say you have 100 shares of [Disney], and you're
interested in making some extra income on these shares by selling a
covered call. [hover over the controls you may need to set]
You'd like to keep the option open for at least a year so you
can be taxed at the long term rate on the premium you collect.
It also works for shorter dated options.

Let's do the scan and see what it finds...
(Type a ticker. Click Scan)

[12 Results]

The Spot is the underlying stock's current price, shown here and on the chart
it's the vertical line.

It found 3 expirations, and you can select each one here in this dropdown.
Selecting a different expiration  will update the chart and two tables below.
The one it selects at first is the expiration with the best option
shown in the bottom table, this one.

You can see the next earnings is [date].
Earnings have a big effect on option volatilty when they're near.

[20 VOLATILITY SURFACE CHART — dots and dashed curve]*

(scroll down to chart)

Now lets take a good look at the chart.

Each dot on this chart is a call for [Dis] at this Expiration, that
meets our scan criteria. 

The bigger green dots are the more attractive options, meaning their
volatility is higher than what the other options suggest it should be.
This expiration only has one attractive option, but look at this one,
it has 4, but none as good as the 1 in the other expiration.

The dashed line is what the option scanner says each
strike's implied volatility *should* be —
to be fancy, it's a fitted volatility surface.

[21 POINT TO GREEN DOTS ABOVE THE LINE]

Again, the green dots are sitting above the line. That means the market
is pricing those options richer than their neighbors. More
premium for the same amount of risk. Those are the calls to consider selling.

(POINT TO RED DOTS BELOW)

The smaller Red dots are the opposite — cheaper than they should be.
If you're buying calls, you'd be interested in those.

(HOVER OVER A DOT — tooltip shows strike, IV+pp, delta)

Hover over any dot, and you get the strike, the expiration, how many
percentage points it sits above the surface, the delta, and the
open interest. Thats valuable info to help decide whether to sell it,
also consider your situation and circumstances.

[22 Like and subscribe Slide]
We'll spend a little more time on the chart, and then go over the 2 tables.
Then we'll talk about what you need to set this up and start using it.
It's quick and easy.
And lastly I'll describe how I made it with Claude.

Please consider liking and subscribing if you're enjoying this content.
---

## WHAT THE TOOL IS DOING (1:15–2:30)

*[30 CHART AGAIN — annotate as you talk]*
Alright, back to the chart...
It provides a great way to see the attractiveness of all options
for a given expiration.

A stock's option chain should form a smooth surface. Plotting the
implied volatility against strike, and it traces a shape — the
volatility smile. Smooth transitions between strikes.
Market makers like to keep it that way.

The dashed line in the chart is that smooth shape, fit to the
chain. When an option's actual IV sits noticeably above the
line, something made it more expensive than its neighbors — a
stale quote, a thin market, event risk that isn't evenly
distributed, or just an inefficiency. That's the option you
want to consider first, to sell.

[31 COLOR LEGEND]*

The color of the dot tells you the gap, in percentage points, between the
actual IV and the fitted surface. We call it IV-plus-pp. Small
gaps — under three percentage points — mean the option is
uniformly priced and the ranking is mostly noise. If you can find some with
Five or more points above the line, it could be a genuine signal.

[32 SCROLL DOWN TO THE TABLES]*

Lets scroll down to the 2 tables.

The first is the chain view. It shows every option in the
expiration selected in the chart dropdown above, sorted by
strike — it's like reading an option chain from your broker with extra
information. The rows are shaded: green means IV+pp is meaningfully above
the average for that expiration, this one.  Gray means it's price is close to its expected
price, and red means the price of the option is less than usual.

So, the shading does the filtering for you —
you can see in seconds which strikes have rich
premium and which ones are unremarkable.

[33 POINT TO YELLOW BID/ASK CELLS]*

Two other shading in the table are Yellow.  Yellow Bid and Ask cells mean
the spread is wider than typical for this chain — spread is the gap
between what buyers will pay and sellers will accept. A wide
spread means your real execution price may land 
worse than the mid-price suggests. Yellow OI or Vol means open
interest or today's volume is low — which makes it harder to
fill at a good price.

Hover over the column headers with yellow shaded cells, and it explains
what the yellow color means.  You can also hover over the IV+pp column header
for a more detailed explanation of it.

[34 POINT TO SECOND TABLE — "TOP CANDIDATES — ALL CHAINS"]*

Let's move down to the top candidates table — the highest-ranked
options by IV+pp pulled from every expiration, all chains are shown here.
The top table showed me everything for single expiration, sorted by strike.
But this table shows me the best ten, regardless of expiration or strike
sorted by IV+pp.

(POINT TO DELTA COLUMN)

Delta is your approximate probability of being assigned at
expiration. A delta of 0.30 means roughly a thirty percent
chance the stock closes above your strike at expiration, for a covered call. 
Lower delta means you keep the stock more often — 
you give up some premium, but there's less chance the stock will
rise above your strike, and you won't lose out on as much
underlying stock appreciation if it gets called away.

[35 POINT TO ANN% COLUMN]*

Ann% is the annualized yield on the premium you'd collect —
for calls, relative to the stock's current price.  It's a good
measure of how much income you'd make by selling the call,
and should usually move in the same direction as delta,
more risk of losing out on underlying gains, means more income.

For puts, Annualized percent is relative to the strike, which is the capital
you'd be putting at risk. 

Annual percent lets you compare options across
different expirations on the same income footing.

---

## A QUICK ASIDE: PERCENTAGE POINTS VS. PERCENT (2:30–3:15)

[40 IV+pp SLIDE WITH THE EXAMPLE NUMBERS]*

Let's talk about IV+PP, the key metric to understand.

This is wonky but an important concept to understand when using
this tool. The IV+pp column you keep seeing — pp stands for
**percentage points**, and that is deliberately different from
percent. They are not the same thing.

Here's why it matters. Implied volatility itself is already a
percentage — forty-five percent, fifty percent, and so on. So
when you talk about the gap between two of those numbers, you
have to be careful. Going from forty-five percent to
forty-eight percent is plus three
**percentage points**. Calling that plus three
**percent** would be wrong — the relative percent change there
is more like plus six-point-seven percent.

Two practical takeaways from that.

**One.** When you read a plus-five-pp signal in the table or
see a green dot floating five units above the fitted curve,
that's an absolute IV gap. Same unit on every strike and every
expiration, which is what makes the ranking comparable across
the whole chain.

**Two.** Do not confuse IV+pp with a return. A plus-five-pp
option is not paying you five percent. The Ann% column on the
table is your actual annualized yield on the premium collected or paid
— that's where you check the real return on capital.

So: pp is the language of volatility differences. Once you've
got that distinction, then you'll have a better understanding of the tool.

---

## Other controls on form

[50 filters]

Let's see what other filters we have to play with...

If you have an existing option you'd like to roll,
check the "Roll an existing" radio.

(CHECK THE ROLL BOX — FIELDS APPEAR)

Fields appear for your current strike and expiration.
I currently have a Dec 140 Disney call.

Let's fill that in.  You have to be accurate with your strike and expiration
if you want accurate Net credit/debit values.

So lets scan, and a Net Credit column appears in the table — the
net credit you'd receive after paying to close the old position
and selling the new position.
Positive means you'd collect cash on the roll. Negative is a
debit.

[51 Dir Type MinMax]
(Switch back to Find new options)

Flip the Direction radio from Sell to Buy. 
Several things invert — you're looking for
the most underpriced options, the dots farthest *below* the
curve. In buy mode the color scale flips — green now means
cheap relative to the surface, so the green dots below the
curve are the candidates.

(Option Type, DTE)

You can view calls, puts, or both with the Option Type radio button.

(CHANGE MIN DTE TO 30, MAX DTE TO 90, SCAN)

Min and Max DTE lets you change the range for Days to Expiration.
Leaving Max DTE as 0 will not set a max DTE.
And you can set Min Open Interest (IO) if you want to make sure
  there is some threshold on Open Interest.

[52 DELTA Top N]

Here's the delta range slider. Default is 0.10 to 0.75 —
a wide range that covers everything from conservative out-of-the-
money strikes to some in-the-money ones. Set this to your preference.

(DRAG SLIDER)

(53 Top N, Scan and Dropdown)

And the Top N value lets you control how many candidates you want to see
in the bottom Top Candidate table across all expirations.

---

## PORTFOLIO SCAN (7:15–8:30)

[60 PORTFOLIO TAB]

The portfolio tab is nice feature that could save you some time
You can upload your entire brokerage transaction log, CSV format  —
it supports Schwab, Robinhood, Fidelity, or Merrill,
   but you have to tell it which format.

(Scan Schwab 556)
The tool detects every open position in the log, and scans each for good options.

This DOES NOT actually upload your transaction log anywhere,
It all stays local.

I'll do one of my schwab logs to demonstrate.

---

## WHAT YOU NEED — SETUP (10:30–12:00)

[70 Setup 1-2 slide]

Now how would you run this yourself.
This is all explained in detail in the Option Scanner Readme.

**Step 1 Get Code from Github

Go to the GitHub repository linked in the description.
Either download the zip or clone it.
Make sure you're in the Stockpile repo.

```
git clone https://github.com/medloh/stockpile.git
cd stockpile
```

You'll need Git installed if you want to clone it


**Step 2 — Install Python.**

You'll need Python 3.12 or newer. Go to python.org, download
and run the installer for your platform. 


[71 Setup 3-4 Slide]

Install UV
*SHOW TERMINAL*

**Step 3 — Install uv.**

This project uses uv, which is a fast Python package manager.
One command installs it:

On Mac or Linux:
```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

On Windows, open PowerShell and run:
```
powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

[Get Deps]
*[SHOW TERMINAL — RUN uv sync]*

**Step 4 — Let UV get all the dependencies.**

From the stockpile directory, run this command:

```
uv sync
```

This installs everything — yfinance, streamlit, etc,
Takes about thirty seconds the first time.


[72 Run it]
SHOW TERMINAL — RUN THE WEB UI COMMAND

**Step 5 — Start the web app.**

From the stockpile folder, one command:

```
uv run streamlit run options-scanner/run_app.py
```

That opens the app in your browser at localhost:8501. From here
on, you don't need the terminal — 
just type in a ticker, hit Scan, and have fun.

Again, The README in the options-scanner folder has the full setup instructions.
Everything in this video is documented there.

**One important thing.**  If you use the portfolio scanner, everything
stays on your machine. It never leaves and Anthropic server sees it.
the only exception is it reaches out to Yahoo Finance to get quotes.

-----

## HOW I BUILT THIS — AND HOW LONG IT TOOK (9:00–10:30)

[80 CLAUDE CODE terminal startup]

Now let me show you what it actually took to build this,
because I think it might surprise you.


I built 95% of this tool — the scanner, the IV surface model, the roll
mode, the portfolio scan, the HTML reports, the Streamlit web
UI — in about 20 back-and-forth messages with Claude Code.


[81 Build prompts slide]

Here's a sample of what those conversations looked like:

> "Thinking of building a tool to look at an option chain and
  help me pick the best option to sell."
> "I want to target LEAPS for long-term capital gains on the
  premium. Note earnings dates."
 
Claude suggests the UI to use and builds it in a few minutes once I confirm.
 
> "How do I run it?"
 
> "Lets add a delta range filter."
> "Lets implement HTML output, buy mode, and short-dated options."
> "How about making a full portfolio scanner from broker transaction logs.
>  we can leverage the code we made for the other tools in this project.
>  Don't stop to ask me anything — just do it."

That's the gist. No architecture meetings, no tickets, no
planning documents. I described what I wanted, Claude built it,
I tested it,  reviewed, came up with new ideas, asked for changes.

A couple more days of polish and here it is.
Claude also helped tremendously with the YouTube script.

[82 continued.]*

Guess who made this slide, it wasn't me.

The result is just under 2000 lines of Python across
ten source files. Option Chain fetching, IV surface fitting, earnings
detection, HTML report generation, portfolio parsing, and the Streamlit app.

95% written part-time in a couple nights.
Then some polish this weekend while working on this YouTube episode.

[83 Before After Claude Slide]

I'm going to make a claim here that I can't prove,
but I believe is in the right ballpark: this took roughly
one 20th the effort it would have taken BC - before Claude.
If I even considered it before, I would have probably given up.

Think about what "before Claude" looks like for a project
like this. You'd spend an evening just researching the right
library for IV surface fitting, reading documentation, looking
at Stack Overflow answers that are three years old and half
wrong. Another evening getting the option chain data into a
usable shape. A weekend on the HTML report. Another session
on the Streamlit UI. You'd hit walls, debug things that
shouldn't be broken, context-switch back to the docs to keep them updated,
and a hundred other things

I didn't do any of that. I described what I wanted. Claude
knew what libraries to use, knew the right mathematical
approach, wrote the boilerplate, and kept all the context
in its head across sessions. My effort was deciding what I
wanted — not figuring out how to build it.  I did occasionally 
coach Claude into better refactorings, and he made a few strange
decisions about things to display.  But easily fixed with iterations.
He messed up just enough so I still can feel useful as a developer,
rather than just an idea man.

That's the shift. The bottleneck used to be implementation.
Now it's just knowing what to ask, and nudging Claude in the 
right direction.

---

[90 Data Source Slide]

**One honest caveat about the data source.** Everything here
comes from Yahoo Finance, which is free and requires no account.
That's a real advantage for getting started. But Yahoo Finance
has limitations.

The implied volatility numbers it returns are sometimes stale
— especially on thinly traded strikes where the last trade was
hours or days ago. The Greeks aren't provided at all; delta
here is calculated from Black-Scholes using Yahoo's IV, which
means if the IV is stale, the delta is too. And for LEAPS
specifically, wide bid-ask spreads and low volume mean some of
the IV readings are noise rather than signal.

None of this breaks the tool — it still surfaces real
patterns — but you should treat the output as a starting
point for further research, not a trading signal on its own.
Always verify the bid-ask spread on you broker before acting on anything
the scanner surfaces. Stale IV also tends to show up as a
single dot far from its neighbors with no obvious reason — if
something looks too good to be true on the chart, it usually is.

A natural future enhancement would be plugging in a better
data source, like the Schwab developer API — free for account
holders — that returns full option chains with real-time
quotes and proper Greeks:  That would make this significantly more accurate,
especially for the IV surface fitting.

It's on my TODO list.

## Disclaimer (read on camera or include in description)
 
[91 Show disclaimer slide]

And the fine print...

DISCLAIMER

This tool is free, open-source software provided as-is with no
warranty of any kind. There is no guarantee of accuracy,
completeness, or fitness for any purpose.

Nothing this tool produces
should be interpreted as a guarantee of any trading outcome.

This is not financial advice. Options trading involves
substantial risk of loss and is not right for every investor.
Do your own research before acting on anything this scanner
surfaces. The author is not responsible for any losses or
other damages from using this software.

## OUTRO (12:00–12:30)

*[92 Thumbnail]*

That's it, hope you find this option scanner useful.
Please leave a comment, good or bad.
Let me know how you're using it, or how I could make it better.

(configure last two episodes to show)
Take a look at my previous two episodes about other tools
in this repo, they should have popped up a few seconds ago.

---

# Not part of the script, YouTube attributes:

## DESCRIPTION

Option Scanner by Claude (Python, GitHub)

Open-source Python Option Scanner with Claude Code on GitHub.
It helps you find the best options to sell or buy — covered calls,
cash-secured puts, rolls, and more. It runs as a web app on your
own laptop, pulls option chains from Yahoo Finance, and ranks
every option by how overpriced or underpriced it is relative to
a fitted volatility surface.

#options #coveredcalls #python #claudecode #optionstrading
#github #leaps #stockmarket #investing #cashsecuredputs

Green dots on the chart mean rich premium worth selling;
red dots mean cheap premium worth buying. The tables
below let you pick your strike with row shading that matches the
chart colors.

**What it does:**
- Volatility-surface chart — every option as a dot, green =
  attractive, red = unattractive, sized by IV excess
- Per-expiration chain view sorted by strike with IV+pp row
  shading — see the whole chain at a glance
- Top candidates table ranked across all expirations
- Yellow cell highlights flag wide spreads, low OI, and low
  volume so you spot execution risk before acting
- Earnings date shown in the chain title with days-to-go count
- Roll mode — enter your current position, see net credit for
  every roll candidate
- Portfolio scan — drag in your brokerage CSV (Schwab,
  Robinhood, Fidelity, or Merrill) and scan every open position
- Buy mode — flips the ranking to find underpriced options
- Filters: delta range, min OI, min/max DTE
- HTML report download for sharing or saving

**Data source:** Yahoo Finance — free, no account or API key
needed. IV can be stale on thinly traded strikes, and Greeks
are computed from Black-Scholes. Treat the output as a starting
point for research, not a trading signal on its own. Always
verify on your broker before acting.

**What you need:**
- Python 3.12+
- uv (free, one-command install)
- The repo (free on GitHub, link below)
- Optional: a brokerage CSV export for the portfolio scan

**Links:**
GitHub repo: https://github.com/medloh/stockpile
Claude Code: https://claude.ai/code
Previous episode (Google Sheets tracker): https://youtu.be/9uf3cyOWPBQ?si=7zstAoL_S4fxIMKm
Previous episode (cost basis charts): https://youtu.be/LqroeMNC7AU?si=sV7y2-UHcXdLc_YI

Your brokerage CSV is processed locally and never leaves your
machine. This tool only calls Yahoo Finance's public API —
no accounts, no keys, no data sent anywhere.

Not financial advice. Options trading involves substantial risk.
Do your own research.

If you hit a snag setting it up, drop a comment — I check them.

**Tags (486 chars):**
options scanner, covered calls, claude code, python, options
trading, leaps options, implied volatility, cash secured puts,
theta gang, option chain, stock options, streamlit, github,
options strategy, call options, put options, volatility surface,
claude ai, open source, options income, rolling options,
portfolio scanner, yahoo finance, anthropic, leaps, ai coding,
covered call strategy, stock market, free tool, thetagang,
options screener, black scholes, finance python, investing

---

## PRODUCTION NOTES

### Before Recording
- **Commit the options-scanner work to git first.** The "how
  I built this" section references the git log and file count —
  you need those to be real and visible on screen. Run:
  `git add options-scanner && git commit -m "Add options-scanner tool"`
  Then use `git log --oneline` and `git diff HEAD~1 --stat` to
  show the scope of what was added in one commit.
- **Have the Streamlit app running before you hit record.** The
  hook depends on it being up the moment you switch to the
  browser. Startup takes 3–4 seconds — don't make viewers wait.
- **Pick a ticker with a visible spread on the chart.** The
  whole hook fails if every dot is sitting on the curve. Before
  recording, scan NVDA, AAPL, TSLA, and 2–3 others — pick the
  one with the most clearly green/red dots away from the line.
  A volatile day or a day before earnings helps.
- If no ticker has a strong spread that day, acknowledge it on
  camera — "today's chains are uniformly priced, which itself
  is useful information; here's what it looks like when there
  IS a signal" — then show a screenshot from a previous day.
- For the chart hook, zoom the browser to ~125% so the dots
  read clearly on a phone screen.
- Pre-generate the HTML report so you can cut straight to it
  without waiting for the download.
- Have a real brokerage CSV ready for the portfolio scan demo
  — redact or blur any sensitive position sizes if needed.
- For the "how I built this" section, decide whether to show
  the actual Claude Code conversation transcript scrolling, or
  just read the prompt summary bullets on screen. The transcript
  is more compelling but harder to read on camera.

### Sections that need strong pacing
- Hook: keep it under 75 seconds — the chart speaks for itself,
  don't over-narrate. The reveal moment is the chart appearing
  with green dots above the curve; let it land.
- Setup section: this will be the hardest for non-technical
  viewers — go slowly, show every keystroke, mention that
  the README has written instructions they can follow at
  their own pace. The payoff is the web app opening — make
  sure that moment is on screen.

### Before Publishing
- Add chapters (timestamps in description)
- Thumbnail set before publishing
- First two lines of description are visible before "show
  more" — make sure they're compelling
- Add cards at 40% and 70% of runtime pointing to the
  Google Sheets and cost basis chart episodes

### After Publishing
- Share to r/thetagang, r/options, r/learnpython,
  r/investing — lead with the scanner output, not the setup
- Pin a comment with the repo link and a prompt:
  "What other signals would make this more useful?"
- Reply to every comment in the first 48 hours
- Add this video to the exit screens of the previous two
  episodes

### Exit Screens
Add to exit screen of:
- Cost basis charts episode
- Google Sheets tracker episode

---

## STARTER COMMENTS

Post one of these pinned or as an early comment to seed the
conversation.

**On the tool itself:**
> What ticker did you scan first? Drop it in the comments —
> curious what IV+pp signals look like across different names
> right now.

**On the data source:**
> Quick question for anyone who's used this: have you noticed
> Yahoo Finance IV being stale on any specific tickers or
> strikes? Trying to build a list of where the data is most
> reliable vs. where to double-check on your broker.

**On features / what's next:**
> What would make this more useful for you? I'm weighing a
> real-time data source (Schwab developer API), earnings
> overlay on the chart, and a few other things. What's your
> priority?

**On the Claude Code angle:**
> I'm genuinely curious — for those of you who code: does the
> "1/20th the effort" claim match your experience with Claude
> Code or similar tools? What's the most useful thing you've
> built with it?

**On setup / getting started:**
> If you run into any issues getting it set up, post here and
> I'll help. Windows, Mac, and Linux should all work — the
> most common snag is the Python PATH setting on Windows during
> install.

**On options strategy:**
> What delta range do you usually target for covered calls?
> I've been using 0.25–0.40 as a default but curious if others
> have a different sweet spot depending on their outlook.


