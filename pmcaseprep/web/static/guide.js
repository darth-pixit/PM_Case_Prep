// The PM Field Guide — a six-chapter, click-through explainer of the PM job.
//
// It is the only surface on the site that needs no account, no mic, and no API
// spend: pure content plus local interaction state. That makes it the natural
// front door — someone who doesn't yet know what a PM does reads this, plays a
// six-round case, and only then has a reason to open the arena.
//
// Implementation notes:
//  * All content lives in CONTENT below, so copy edits never touch render code.
//  * State is a single object; any change re-renders the active screen. The page
//    is small enough that a full re-render is simpler and faster than diffing.
//  * The chapter is kept in location.hash, so links are shareable, the back
//    button works, and PostHog sees a real path per chapter.

(() => {
  "use strict";

  const track = PMCP.experiment("guide").track;
  const esc = PMCP.esc;

  // ── content ───────────────────────────────────────────────────────────────

  const SCREENS = [
    ["home", "Start"],
    ["role", "The Role"],
    ["types", "Flavors"],
    ["decisions", "Legendary Calls"],
    ["cases", "You're the PM"],
    ["skills", "Skill Map"],
    ["breakin", "Break In"],
  ];

  const CONTENT = {
    homeCards: [
      { stat: "1", title: "The job, decoded", sub: "What a PM actually does all day — and the myths that get it wrong.", go: "role" },
      { stat: "6", title: "Flavors of PM", sub: "Consumer, B2B, growth, AI… find the one that fits how you think.", go: "types" },
      { stat: "5", title: "Legendary calls", sub: "Netflix autoplay. Uber surge. The decisions behind the products.", go: "decisions" },
      { stat: "6", title: "Rounds you play", sub: "One real problem, six decisions — you run the quarter as the PM.", go: "cases" },
    ],

    pillars: [
      { n: "01", title: "Decide what to build", body: "Turn a fog of ideas, requests, and data into a ranked list of bets — and defend why #1 is #1." },
      { n: "02", title: "Talk to users, constantly", body: "Interviews, support tickets, watching people struggle. Evidence beats opinion in every argument." },
      { n: "03", title: "Rally the team", body: "Write the story of where you're going so clearly that engineers and designers make good calls without you in the room." },
      { n: "04", title: "Ship, measure, repeat", body: "Launch is the midpoint, not the finish. Did it work? The metric answers, and the next bet begins." },
    ],

    day: [
      { time: "9:00", title: "Standup", body: "15 minutes with engineers and designers. What shipped, what's blocked, what needs a decision by noon." },
      { time: "9:30", title: "Dashboard check", body: "Yesterday's launch moved signups +4%. But activation dipped. Why? A thread to pull." },
      { time: "10:00", title: "User interview", body: "Watching a customer try the new flow. She gets stuck exactly where you feared. Painful. Gold." },
      { time: "11:30", title: "Spec writing", body: "The quiet craft: a two-page doc that turns \"we should improve search\" into something buildable." },
      { time: "1:00", title: "Trade-off meeting", body: "Engineering says the elegant version takes 6 weeks; the scrappy one takes 2. You choose scrappy, and write down why." },
      { time: "3:00", title: "Stakeholder pitch", body: "Convincing sales leadership why their #1 request is #4 on the roadmap. Data helps. Storytelling helps more." },
      { time: "4:30", title: "Deep work", body: "Analyzing the activation dip. Turns out it's one confusing button. Tomorrow's standup has its topic." },
    ],

    myths: [
      { myth: "\"The PM is the boss of the team.\"", reality: "Nobody reports to the PM. You lead by being right often, transparent always, and useful daily." },
      { myth: "\"PMs need to code.\"", reality: "You need technical fluency — enough to ask good questions and understand trade-offs. Most PMs don't write production code." },
      { myth: "\"PMs come up with all the ideas.\"", reality: "Ideas are everywhere — users, engineers, data. The rare skill is choosing, sequencing, and saying no with a straight face." },
    ],

    pmTypes: [
      { name: "Consumer PM", tag: "Apps millions use", own: "Engagement, retention, delight. You obsess over what makes people come back tomorrow.", example: "The Spotify PM deciding whether Discover Weekly refreshes Monday or Friday.", thrives: "People with taste, empathy, and a love of behavioral detail." },
      { name: "B2B / Enterprise PM", tag: "Software companies buy", own: "Workflows, admin controls, contracts worth millions. Fewer users, higher stakes per user.", example: "A Salesforce PM redesigning permissions so a 40,000-person bank can adopt the product.", thrives: "People who enjoy deep customer conversations and complex domains." },
      { name: "Technical / Platform PM", tag: "Products for developers", own: "APIs, infrastructure, internal platforms. Your users write code.", example: "A Stripe PM deciding what the payments API should do when a card is declined mid-subscription.", thrives: "Ex-engineers and systems thinkers who like precision." },
      { name: "Growth PM", tag: "The science of more", own: "Signup flows, onboarding, pricing pages, referral loops. Everything measured, everything tested.", example: "The Dropbox PM behind \"give a friend 500MB, get 500MB\" — one loop that drove 3900% growth in 15 months.", thrives: "Analytical, experimental, slightly impatient people." },
      { name: "AI / ML PM", tag: "Products that learn", own: "Model behavior, evals, the line between magical and creepy. The newest, fastest-growing flavor.", example: "A PM deciding when an AI assistant should say \"I don't know\" instead of guessing.", thrives: "People comfortable with probability instead of certainty." },
      { name: "Internal / Ops PM", tag: "Tools for your own company", own: "The systems employees use to serve customers — support consoles, logistics tools.", example: "An Amazon PM improving the tool warehouse workers use to locate items, saving seconds a million times a day.", thrives: "Pragmatists who love visible, immediate impact." },
    ],

    stories: [
      {
        title: "Autoplay: the 5-second countdown", company: "Netflix, 2012",
        hook: "The most consequential feature of the streaming era was a timer.",
        setup: "Binge-watching existed, but every episode ended with a decision: keep going or stop? Decisions are friction.",
        call: "Auto-play the next episode after a short countdown. Make continuing the default and stopping the effortful act.",
        lens: "A default is a product decision with more power than any feature. The PM had to weigh engagement (way up) against user control (quietly eroded) — a trade-off still debated today.",
        next: "Autoplay became the industry standard — YouTube, HBO and Disney+ all followed. In 2019, after years of criticism, Netflix finally shipped a setting to turn it off: a reminder that engagement wins carry user-trust debt, and PMs pay it back later.",
        lesson: "Whoever designs the default decides what most people do.",
      },
      {
        title: "Surge pricing: charging more on purpose", company: "Uber, 2011",
        hook: "The feature everyone hates — that everyone copied.",
        setup: "New Year's Eve: everyone wants a ride, no drivers on the road. The app is technically fine and practically useless.",
        call: "Raise prices when demand spikes — publicly, in the app. Higher fares pull more drivers onto the road until wait times recover.",
        lens: "The insight: the product isn't the app, it's the marketplace. Reliability at 2am IS the feature, and price is the lever that delivers it — even though users hate seeing 2.1x.",
        next: "Surge outlived the outrage and became core to every marketplace since: DoorDash peak pay, Lyft Prime Time, dynamic event pricing. Uber later fixed the story rather than the mechanism — upfront fixed fares replaced the scary 2.1x multiplier. Same economics, calmer humans.",
        lesson: "Sometimes the right product decision is the unpopular one that keeps the promise.",
      },
      {
        title: "Stories: the billion-dollar copy", company: "Instagram, 2016",
        hook: "Sometimes the best call is admitting someone else was right.",
        setup: "Snapchat Stories was pulling teens away. Instagram posts felt too permanent — people stopped sharing casually.",
        call: "Build Stories, nearly identically, and put it above the feed. No shame, no disguise.",
        lens: "The PM question wasn't \"is copying bad?\" It was \"our users have a job — casual, disappearing sharing — and they're hiring another app to do it.\" Distribution + speed beat originality.",
        next: "Within a year, Instagram Stories alone had 250M daily users — more than all of Snapchat — and Snap's growth stalled the quarter after launch. It's now the textbook fast-follow, studied in every PM course as proof that distribution plus speed can beat originality.",
        lesson: "You don't get points for novel. You get points for solved.",
      },
      {
        title: "1-Click: deleting the checkout", company: "Amazon, 1997",
        hook: "A billion-dollar patent for deleting three screens.",
        setup: "Every checkout step loses buyers. Cart, address, card, confirm — each screen is a chance to reconsider.",
        call: "Store everything, add one button: buy it now. Ship it before anyone asks for it — nobody was requesting \"fewer confirmation screens.\"",
        lens: "Users can't articulate friction; they just quietly leave. Watching behavior (abandonment) beat asking for opinions. Amazon considered it so valuable they patented it.",
        next: "The patent held for 20 years — Apple chose to license it rather than fight it. When it expired in 2017, retailers everywhere copied it within months, and its DNA lives on in every Buy Now button, one-tap checkout and \"save my card\" flow you've ever used.",
        lesson: "Count the steps. Every one you delete is revenue.",
      },
      {
        title: "Discover Weekly: the hack that became the brand", company: "Spotify, 2015",
        hook: "A hack-week experiment became the company's moat.",
        setup: "Spotify had world-class ML generating playlists — used mostly by nobody. Great tech, no story.",
        call: "Package it as a personal gift: one playlist, just for you, every Monday morning. Scarcity and ritual, not a settings page.",
        lens: "The technology existed for years. The product decision was the framing — \"your weekly mixtape\" — which turned an algorithm into a relationship. 40M users in the first year.",
        next: "Discover Weekly hit 40M listeners in its first year and spawned a family — Release Radar, Daily Mixes and eventually Wrapped, the most shared product moment of every year. Strategically it changed the company: personalization became Spotify's answer to rivals with bigger catalogs and deeper pockets.",
        lesson: "Packaging isn't decoration. Often it IS the product.",
      },
    ],

    rounds: [
      {
        ask: "Your first move?",
        info: "Day 1. The CEO forwarded the dashboard with \"fix this\" in the subject line. Everyone has a theory. You have twelve weeks.",
        options: [
          { text: "Propose discounted shipping — go straight at the obvious cause", verdict: "trap", feedback: "You just prescribed before diagnosing. Discounts cost real margin, and you still don't know whether price is even the problem. Great PMs are slow to solutions and fast to questions." },
          { text: "Ask the data team exactly which step shoppers quit on", verdict: "best", feedback: "Right instinct: find the leak before you plug it. A step-by-step breakdown costs a day and might save the quarter. It comes back: nearly everyone quits on the exact screen where the delivery cost first appears." },
          { text: "Call a cross-team workshop to brainstorm fixes", verdict: "ok", feedback: "Team-spirited, but too early — you'd be brainstorming without facts. A workshop only amplifies the facts you bring; bring none and you get loud opinions. Get the numbers first." },
        ],
      },
      {
        ask: "The drop happens right when shipping cost appears. What do you ask next?",
        info: "So it's the moment costs show up. But is the problem the amount — or the ambush?",
        options: [
          { text: "Ask: does abandonment change when delivery is cheap vs expensive?", verdict: "best", feedback: "Exactly the question that settles it. The data comes back: people quit at nearly the same rate whether delivery costs $2 or $12. It's not the price — it's the surprise. You just found the real enemy." },
          { text: "Email a survey: \"Why didn't you complete your purchase?\"", verdict: "ok", feedback: "Surveys are fine but slow and unreliable here — people rationalize after the fact (\"too expensive\") even when their behavior says otherwise. The behavioral data can answer this faster and more honestly." },
          { text: "Skip the questions — start haggling with delivery firms for cheaper rates", verdict: "trap", feedback: "Months of delivery-contract work, resting on a guess nobody checked. If the real issue is surprise, cheaper rates won't move the number at all. One database query would have told you." },
        ],
      },
      {
        ask: "It's surprise, not price. What do you build?",
        info: "New picture: users feel ambushed at the last step. The fix should kill the surprise as early as possible.",
        options: [
          { text: "Show an estimated delivery cost right on the product page", verdict: "best", feedback: "The smallest change that goes straight at what you found: users see the full picture before they emotionally commit. Cheap to build, easy to test on half your shoppers, fast to learn from." },
          { text: "Redesign the whole checkout into one premium page", verdict: "trap", feedback: "A quarter-long bet that buries your one clear insight under fifty other changes — if the number moves, you won't know why. Big redesigns are where sharp diagnoses go to die." },
          { text: "Add a \"Free shipping over $50\" banner to grow cart size", verdict: "ok", feedback: "A reasonable revenue lever, but it sidesteps your diagnosis: the ambush is still there for everyone under $50. Might help the business; won't fix the cliff." },
        ],
      },
      {
        ask: "Engineering pushback: exact prices need a postcode you don't have at browse time. Now what?",
        info: "Your clean fix just hit reality. Exact delivery prices need an address you don't have yet.",
        options: [
          { text: "Show a range instead: \"Delivery: $4–8\"", verdict: "best", feedback: "Good enough now beats perfect later. A range kills 90% of the surprise for 10% of the effort, and you find out this fortnight instead of next year. Precision can come later — if it's even needed." },
          { text: "Pause it until the site can work out the shopper's postcode", verdict: "trap", feedback: "You just traded a two-week test for a six-month wait on someone else. Waiting for perfect data is how promising fixes quietly die on roadmaps." },
          { text: "Show one flat average: \"Most orders deliver for about $6\"", verdict: "ok", feedback: "Workable — but averages mislead anyone buying something bulky, who'll now feel ambushed twice. The range is barely more work and stays honest with everyone." },
        ],
      },
      {
        ask: "One week into the A/B test: 18% fewer people are quitting… but total sales look flat. The CEO wants an update. What do you say?",
        info: "The metric you targeted moved. The metric the company cares about didn't. Something's hiding.",
        options: [
          { text: "\"Give me two days — I want to split the results up first\"", verdict: "best", feedback: "A flat average often hides two opposite stories. You split it up: phone sales are clearly up, computer sales slightly down — the estimate crowds the page there. That's a real insight, not noise." },
          { text: "Declare victory — fewer people quitting was the goal, and that happened", verdict: "trap", feedback: "You'd be reporting the metric you moved instead of the result the company actually needs. CEOs remember the PM whose \"win\" never showed up in revenue. Never celebrate before you split the numbers up." },
          { text: "Extend the test another month for more confidence", verdict: "ok", feedback: "More data isn't the problem — data nobody has broken apart is. The answer is already sitting in the groups. Split the data first; extend only if it's still genuinely ambiguous." },
        ],
      },
      {
        ask: "Phones win clearly; computers are flat to slightly worse. Final call of the quarter: ship it?",
        info: "Marketing wants an announcement. Engineering wants a decision. Twelve weeks are up.",
        options: [
          { text: "Release it on phones now; keep working on the computer version", verdict: "best", feedback: "Break the decision in two — take the win where it's proven, keep working where it isn't. You shipped a measurable improvement inside one quarter with a clear next step. That's the job, done well." },
          { text: "Release it everywhere — computers are only slightly worse", verdict: "ok", feedback: "Defensible if speed matters most, but you're knowingly shipping a small regression to half your users when releasing to phones only costs almost nothing extra." },
          { text: "Hold everything until computers win too", verdict: "trap", feedback: "You're holding a proven win on phones hostage to a problem on computers. Users lose value every week it waits. Ship what works; fix the rest." },
        ],
      },
    ],

    idealSteps: [
      "Work out what's wrong before you prescribe a cure — pull the step-by-step numbers and find exactly where people leave.",
      "Ask the one question that settles it: do people quit more when delivery costs more? (They didn't — the surprise was the problem, not the price.)",
      "Build the smallest thing that fixes what you found: show the cost before people get their hopes up.",
      "Trade exactness for speed — a $4–8 range goes live in a fortnight; exact prices can come later.",
      "Split the numbers up before celebrating: the flat average hid a win on phones and a dip on computers.",
      "Break the final call in two — release the proven win now, keep working on the rest.",
    ],

    missed: [
      "The most valuable moves cost nothing to build: one look at the numbers, one comparison, one split. The power was in the questions, not the code.",
      "Every trap had the same shape — acting on a hunch that one day of checking would have settled.",
      "The goal never changed; only what you knew did. Good PMs re-plan every time reality answers back.",
    ],

    quick: [
      {
        title: "The Loud Minority",
        scenario: "Your most vocal power users are demanding dark mode — loudly, on social media. Meanwhile your data shows 40% of new users never finish onboarding. Your team can only do one this quarter.",
        hint: "Reach × impact. Who benefits, and how much?",
        options: [
          { text: "Ship dark mode — the community is asking and it builds goodwill", verdict: "trap", feedback: "The loudest voices are rarely the most representative. Power users will stay either way; the 40% who bounce at onboarding are gone forever. Vocal ≠ important is one of the hardest PM lessons." },
          { text: "Fix onboarding — the funnel leak affects every future user", verdict: "best", feedback: "Right. Every user flows through onboarding; a 40% leak compounds forever. A PM's core move is prioritizing by reach × impact, not volume of requests. Tell the community honestly when dark mode is coming — transparency buys patience." },
          { text: "Split the team and do both halfway", verdict: "ok", feedback: "The compromise that pleases no one. Half a fixed funnel and half a dark mode usually means two unfinished things. Focus is a feature — saying \"not yet\" clearly is more respected than doing everything badly." },
        ],
      },
      {
        title: "Ship or Slip",
        scenario: "Launch is Friday. Marketing is queued, a partner announcement is scheduled. Thursday night, QA finds a bug: in a rare flow, users see someone else's first name on a receipt. No payment data exposed. Ship or slip?",
        hint: "Severity isn't about frequency. It's about what kind of wrong.",
        options: [
          { text: "Ship — it's rare, log it, hotfix next week", verdict: "trap", feedback: "\"Rare\" is doing a lot of work in that sentence. This isn't a cosmetic bug — it's a privacy leak, however small. Trust breaks in one screenshot on social media. PMs triage by severity of consequence, not frequency of occurrence." },
          { text: "Slip the launch, fix it, reschedule everything", verdict: "ok", feedback: "Defensible and safe — but possibly over-correcting. A full slip burns partner trust and momentum. Before paying that price, a good PM asks: can we cut the affected flow instead of the whole launch?" },
          { text: "Ship, but disable the rare flow behind a flag until it's fixed", verdict: "best", feedback: "This is the pro move: decompose the decision. The launch and the bug live in one flow — separate them. Feature flags exist exactly for this. You keep the date, protect users, and fix it calmly next week." },
        ],
      },
    ],

    skills: [
      { name: "User empathy & research", why: "Every good decision starts with understanding a human problem better than anyone else in the room.", how: "Interview 5 friends about an app they use daily. Ask \"walk me through the last time you…\" — never \"would you use…\". Write up what surprised you." },
      { name: "Prioritization", why: "Resources are always finite. The job is choosing — and surviving the disappointment of everyone whose thing you didn't choose.", how: "Take any app's last 10 updates (App Store release notes). Rank them by reach × impact ÷ effort. Now defend your top pick in writing." },
      { name: "Communication & storytelling", why: "A PM's only real output is a decision other people act on. If you can't make it land, it didn't happen.", how: "Write a one-page memo arguing for one change to a product you love. Structure: problem, evidence, proposal, what we'd measure. Send it to a friend." },
      { name: "Data literacy", why: "Metrics are how products talk back. You need to hear them — and know when they're lying.", how: "Learn spreadsheet basics + one funnel: visit → signup → activation → retention. Free: Google Analytics demo account, or any SQL intro course." },
      { name: "Technical fluency", why: "You don't write the code, but you negotiate with people who do. Understanding trade-offs earns their respect.", how: "Build one tiny thing end-to-end — a no-code app or a simple website with an AI assistant. The goal is feeling why \"small change\" is sometimes huge." },
      { name: "Execution & judgment", why: "Plans are easy; shipping through ambiguity, dependencies, and Thursday-night bugs is the sport.", how: "Run any small project start-to-finish — an event, a newsletter, a side product. Write a retro: what slipped, what you'd do differently." },
    ],

    resumeTips: [
      { title: "Outcomes, not duties", body: "\"Reduced onboarding drop-off 18% by simplifying signup\" beats \"responsible for onboarding.\" Every line: verb, action, measurable result." },
      { title: "Reframe what you already did", body: "Organized anything? Prioritized under constraints? Persuaded without authority? That's PM work — name it that way, whatever your title was." },
      { title: "Attach proof", body: "Link 2–3 product teardowns or a case study you wrote. An applicant with visible thinking beats a resume adjective every time." },
    ],

    interviews: [
      { name: "Product sense", framework: "User → problem → solutions → trade-offs", question: "How would you improve Google Maps for tourists?", approach: "Don't jump to features. Pick a user, name their sharpest problem, propose 2–3 solutions, choose one and say why. Structure is the answer." },
      { name: "Execution & metrics", framework: "Funnel thinking + hypothesis testing", question: "DAU dropped 10% overnight. What do you do?", approach: "Segment before you speculate: which platform, region, user type? Rule out logging bugs first. Show you debug systematically, not anxiously." },
      { name: "Behavioral", framework: "STAR: situation, task, action, result", question: "Tell me about a time you disagreed with your team.", approach: "Pick real stories with tension in them. What interviewers grade: did you use evidence, did you listen, did you commit once decided?" },
      { name: "Strategy", framework: "Market → moat → bet", question: "Should Spotify get into audiobooks?", approach: "Zoom out: what does the company uniquely own (ears, habits, data)? Argue from that advantage, name the risk honestly, then take a side." },
    ],

    resourceCols: [
      {
        label: "Read first",
        items: [
          { name: "Inspired — Marty Cagan", note: "The canonical \"what great product teams do\" book." },
          { name: "Continuous Discovery Habits — Teresa Torres", note: "How to actually talk to users, weekly." },
          { name: "Escaping the Build Trap — Melissa Perri", note: "Why shipping features ≠ making progress." },
        ],
      },
      {
        label: "Follow along",
        items: [
          { name: "Lenny's Newsletter & Podcast", note: "The industry water cooler. Start with the most popular episodes." },
          { name: "Stratechery — Ben Thompson", note: "Strategy thinking, one essay at a time." },
          { name: "Product teardowns on YouTube", note: "Watch PMs critique real products; then do your own." },
        ],
      },
      {
        label: "Practice & prep",
        items: [
          { name: "Exponent / Tryexponent", note: "Mock PM interviews with real question banks." },
          { name: "Cracking the PM Interview — McDowell", note: "The interview-prep classic." },
          { name: "A community (Product School, local PM meetups)", note: "One warm referral outperforms fifty cold applications." },
        ],
      },
    ],

    plan: [
      { week: "Days 1–7", title: "See the job", body: "Read Inspired. Listen to 3 Lenny episodes. Write one paragraph: which PM flavor pulls you, and why." },
      { week: "Days 8–14", title: "Think the job", body: "Write 2 product teardowns (1 page each). Interview 3 people about a product they use daily." },
      { week: "Days 15–21", title: "Do the job", body: "Pick one problem from your interviews. Write a mini spec: problem, evidence, solution, success metric." },
      { week: "Days 22–30", title: "Show the job", body: "Polish your best teardown + spec into a small portfolio. Rewrite your resume with outcomes. Do 2 mock interviews." },
    ],
  };

  const CHIP = {
    best: { label: "Strong call", bg: "var(--color-accent-2-200)", color: "var(--color-accent-2-800)" },
    ok: { label: "Defensible", bg: "var(--color-neutral-200)", color: "var(--color-neutral-800)" },
    trap: { label: "Watch out", bg: "var(--color-accent-200)", color: "var(--color-accent-800)" },
  };

  // ── state ─────────────────────────────────────────────────────────────────

  // `showHints` is the design's authoring prop, exposed as ?hints=1 so the hint
  // line above each quick-fire can be demoed without a rebuild.
  const showHints = new URLSearchParams(location.search).get("hints") === "1";

  const S = {
    screen: "home",
    visited: { home: true },
    selectedType: 0,
    expandedStory: 0,
    answers: {},   // quick-fire index -> option index
    planOpen: false,
    round: 0,      // 0..6; 6 means the case is finished
    picks: {},     // round index -> option index
    reveal: false,
  };

  const set = (patch) => { Object.assign(S, patch); render(); };

  function go(screen, opts) {
    if (!SCREENS.some(([k]) => k === screen)) screen = "home";
    S.visited[screen] = true;
    S.screen = screen;
    if (!(opts && opts.fromHash)) location.hash = screen === "home" ? "" : screen;
    track("screen_viewed", { screen, explored: Object.keys(S.visited).length });
    render();
    window.scrollTo(0, 0);
  }

  // ── render helpers ────────────────────────────────────────────────────────

  const el = (id) => document.getElementById(id);

  // Every interactive element declares data-act (+ optional data-i/data-j);
  // one delegated listener on <main> routes them, so re-rendering never leaks
  // handlers.
  const act = (name, i, j) =>
    `data-act="${name}"${i === undefined ? "" : ` data-i="${i}"`}${j === undefined ? "" : ` data-j="${j}"`}`;

  const optionHTML = (o, j, picked, scope, i) => {
    const isPicked = picked === j;
    const c = CHIP[o.verdict];
    return `
      <div>
        <button class="g-opt${isPicked ? " is-picked" : ""}" ${act(scope, i, j)}
                aria-pressed="${isPicked}">
          <span class="g-opt-letter">${String.fromCharCode(65 + j)}</span>
          <span class="g-opt-text">${esc(o.text)}</span>
          ${isPicked ? `<span class="g-opt-badge" style="background:${c.bg};color:${c.color};">${c.label}</span>` : ""}
        </button>
        ${isPicked ? `<div class="g-feedback" style="border-left-color:${c.color};">${esc(o.feedback)}</div>` : ""}
      </div>`;
  };

  const runItem = (j, cls) => `
    <div class="${cls}">
      <div class="g-run-n">Round ${j.n}</div>
      <div class="g-run-choice">${esc(j.choice)}</div>
      <span class="g-chip" style="background:${j.chip.bg};color:${j.chip.color};">${j.chip.label}</span>
    </div>`;

  const journey = () =>
    CONTENT.rounds.slice(0, S.round).map((r, i) => {
      const o = r.options[S.picks[i]] || r.options[0];
      return { n: i + 1, choice: o.text, chip: CHIP[o.verdict] };
    });

  // ── screens ───────────────────────────────────────────────────────────────

  const screens = {
    home: () => `
      <div class="g-hero">
        <div class="g-badge">A field guide to product management</div>
        <h1>Nobody reports to them. Everything depends on them.</h1>
        <p>Every product you love — the playlist that reads your mind, the ride that shows up in three minutes — exists because someone decided <em>what</em> to build, convinced a team it mattered, and stayed up worrying whether it worked.</p>
        <p>That someone is a product manager. Here's what the job really is — and how people like you get into it.</p>
        <button class="btn btn-primary g-cta-lg" ${act("go-role")}>Start the story →</button>
      </div>
      <div class="g-grid g-grid-220 g-home-cards">
        ${CONTENT.homeCards.map((c, i) => `
          <button class="g-card g-home-card" ${act("home-card", i)}>
            <div class="g-home-stat">${esc(c.stat)}</div>
            <div class="g-home-title">${esc(c.title)}</div>
            <div class="g-home-sub">${esc(c.sub)}</div>
          </button>`).join("")}
      </div>`,

    role: () => `
      <div style="max-width:680px;">
        <div class="g-kicker">Chapter 1 · The role</div>
        <h1 class="g-chapter-h1" style="margin-bottom:18px;">The job, in one sentence</h1>
        <div class="g-card g-statement">A PM figures out <span class="hi">what to build and why</span>, then makes sure it actually ships — without writing the code or managing the people.</div>
        <p class="g-role-note">They lead through evidence and persuasion, not authority. Engineers build it, designers shape it, the PM owns the question: <em>is this the right thing to build at all?</em></p>
      </div>

      <h2 class="g-h2">Four things a PM actually does</h2>
      <div class="g-grid g-grid-230" style="margin-bottom:52px;">
        ${CONTENT.pillars.map((p) => `
          <div class="g-card g-pillar">
            <div class="g-pillar-n">${esc(p.n)}</div>
            <div class="g-pillar-t">${esc(p.title)}</div>
            <div class="g-pillar-b">${esc(p.body)}</div>
          </div>`).join("")}
      </div>

      <h2 class="g-h2" style="margin-bottom:6px;">A Tuesday, hour by hour</h2>
      <p class="g-h2-lede" style="max-width:600px;">No two days match, but this one is honest.</p>
      <div class="g-card g-day">
        ${CONTENT.day.map((s) => `
          <div class="g-slot">
            <div class="g-slot-time">${esc(s.time)}</div>
            <div class="g-slot-body"><b>${esc(s.title)}</b><span> — ${esc(s.body)}</span></div>
          </div>`).join("")}
      </div>

      <h2 class="g-h2">Myths, meet reality</h2>
      <div class="g-myths">
        ${CONTENT.myths.map((m) => `
          <div class="g-card g-myth">
            <div class="g-myth-side">
              <div class="g-label g-label-a">Myth</div>
              <div class="g-val">${esc(m.myth)}</div>
            </div>
            <div class="g-myth-real">
              <div class="g-label g-label-2">Reality</div>
              <div class="g-val">${esc(m.reality)}</div>
            </div>
          </div>`).join("")}
      </div>

      <button class="btn btn-primary" ${act("go-types")}>Next: the many flavors of PM →</button>`,

    types: () => {
      const d = CONTENT.pmTypes[S.selectedType];
      return `
      <div class="g-intro">
        <div class="g-kicker">Chapter 2 · The flavors</div>
        <h1 class="g-chapter-h1">"PM" isn't one job. It's six.</h1>
        <p>Same core craft, wildly different days. Tap each one — knowing which flavor fits you is half of breaking in.</p>
      </div>
      <div class="g-types">
        ${CONTENT.pmTypes.map((t, i) => `
          <button class="g-type${S.selectedType === i ? " is-on" : ""}" ${act("type", i)}
                  aria-pressed="${S.selectedType === i}">
            <div class="g-type-n">${esc(t.name)}</div>
            <div class="g-type-tag">${esc(t.tag)}</div>
          </button>`).join("")}
      </div>
      <div class="g-card g-type-detail">
        <h2>${esc(d.name)}</h2>
        <div class="lead">${esc(d.tag)}</div>
        <div class="g-cols">
          <div><div class="g-label">What you own</div><div class="g-val">${esc(d.own)}</div></div>
          <div><div class="g-label">A real example</div><div class="g-val">${esc(d.example)}</div></div>
          <div><div class="g-label">Who thrives here</div><div class="g-val">${esc(d.thrives)}</div></div>
        </div>
      </div>
      <button class="btn btn-primary" ${act("go-decisions")}>Next: legendary calls →</button>`;
    },

    decisions: () => `
      <div class="g-intro">
        <div class="g-kicker">Chapter 3 · Legendary calls</div>
        <h1 class="g-chapter-h1">Five decisions that changed everything</h1>
        <p>Behind every "obvious" feature is a moment when it wasn't obvious at all. Open each story to see the call through a PM's eyes.</p>
      </div>
      <div class="g-stories">
        ${CONTENT.stories.map((s, i) => {
          const open = S.expandedStory === i;
          return `
          <div class="g-card g-story">
            <button class="g-story-head" ${act("story", i)} aria-expanded="${open}">
              <div class="g-story-n">0${i + 1}</div>
              <div class="g-story-mid">
                <div class="g-story-t">${esc(s.title)}</div>
                <div class="g-story-sub">${esc(s.company)} · <em>${esc(s.hook)}</em></div>
              </div>
              <div class="g-chevron">${open ? "−" : "+"}</div>
            </button>
            ${open ? `
            <div class="g-story-body">
              <div class="g-story-grid">
                <div><div class="g-label">The setup</div><div class="g-val">${esc(s.setup)}</div></div>
                <div><div class="g-label">The call</div><div class="g-val">${esc(s.call)}</div></div>
                <div><div class="g-label">The PM lens</div><div class="g-val">${esc(s.lens)}</div></div>
                <div><div class="g-label g-label-2">What happened next</div><div class="g-val">${esc(s.next)}</div></div>
              </div>
              <div class="g-lesson">Lesson: ${esc(s.lesson)}</div>
            </div>` : ""}
          </div>`;
        }).join("")}
      </div>
      <button class="btn btn-primary" ${act("go-cases")}>Next: your turn to decide →</button>`,

    cases: () => {
      const done = S.round >= 6;
      const R = Math.min(S.round, 5);
      const round = CONTENT.rounds[R];
      const picked = S.picks[R];
      const runs = journey();
      const tally = { best: 0, ok: 0, trap: 0 };
      for (let i = 0; i < S.round; i++) {
        const o = CONTENT.rounds[i].options[S.picks[i]];
        if (o) tally[o.verdict]++;
      }

      const live = `
        <div class="g-round-wrap">
          <div class="g-card g-round">
            <div class="g-round-info">${esc(round.info)}</div>
            <div class="g-round-ask">${esc(round.ask)}</div>
            <div class="g-opts">
              ${round.options.map((o, j) => optionHTML(o, j, picked, "round-pick", R)).join("")}
            </div>
            ${picked !== undefined ? `
              <button class="btn btn-primary" style="margin-top:18px;" ${act("continue")}>
                ${S.round === 5 ? "Lock it in — finish the case →" : "Lock it in, continue →"}
              </button>` : ""}
          </div>
          <aside class="g-card g-run">
            <div class="g-label g-label-2">Your run so far</div>
            ${runs.length === 0
              ? `<div class="g-run-empty">Your calls stack up here as you go — the story you'll tell the team at the end.</div>`
              : `<div class="g-run-list">${runs.map((j) => runItem(j, "g-run-item")).join("")}</div>`}
          </aside>
        </div>`;

      const finished = `
        <div class="g-card g-done">
          <div class="g-done-t">The quarter's over. Here's your run.</div>
          <div class="g-tally">${tally.best} strong calls · ${tally.ok} defensible · ${tally.trap} to watch out for</div>
          <div class="g-grid g-grid-240 g-done-cards">
            ${runs.map((j) => runItem(j, "g-done-card")).join("")}
          </div>
          <div class="g-done-actions">
            <button class="btn btn-primary" ${act("reveal")}>${S.reveal ? "−" : "+"} The ideal run — and what's easy to miss</button>
            <button class="btn btn-secondary" ${act("restart")}>Play the quarter again</button>
          </div>
          ${S.reveal ? `
          <div class="g-reveal">
            <div class="g-label g-label-2" style="letter-spacing:0.12em;margin-bottom:12px;">The ideal run</div>
            <div class="g-steps">
              ${CONTENT.idealSteps.map((t, i) => `
                <div class="g-step"><div class="g-step-n">${i + 1}</div><div class="g-step-t">${esc(t)}</div></div>`).join("")}
            </div>
            <div class="g-label g-label-a" style="letter-spacing:0.12em;margin-bottom:12px;">What's easy to miss</div>
            <div class="g-missed">${CONTENT.missed.map((t) => `<div>${esc(t)}</div>`).join("")}</div>
          </div>` : ""}
        </div>`;

      return `
      <div class="g-intro">
        <div class="g-kicker">Chapter 4 · You're the PM</div>
        <h1 class="g-chapter-h1">One problem. Six decisions. Your quarter.</h1>
        <p>This is a case you play. The mission never changes — but every call you make changes what you know for the next one. Pick, see how a seasoned PM would think about it, then carry your choices forward. At the end, compare your run to the ideal one.</p>
      </div>

      <div class="g-dark g-brief">
        <div class="g-label">The brief</div>
        <div class="g-brief-t">7 out of 10 shoppers now quit at the payment step. Fix it this quarter.</div>
        <div class="g-brief-b">You're the PM of an online shop. Five engineers, one designer, twelve weeks. The mission stays the same all the way through — what changes is what you know.</div>
        <div class="g-brief-b" style="margin-top:10px;opacity:0.85;">💡 Hit a word you don't know? Select it — anywhere on this page — and we'll explain it in plain English.</div>
      </div>

      <div class="g-pips">
        ${CONTENT.rounds.map((_, i) => `
          <div class="g-pip${i < S.round ? " is-done" : i === S.round ? " is-now" : ""}">${i + 1}</div>`).join("")}
        <span class="g-pips-label">Round ${done ? 6 : S.round + 1} of 6</span>
      </div>

      ${done ? finished : live}

      <h2 class="g-h2-sm" style="margin-bottom:6px;">Quick-fire: two more calls</h2>
      <p class="g-h2-lede" style="margin-bottom:16px;">One pick each — different products, same discipline.</p>
      <div class="g-quicks">
        ${CONTENT.quick.map((c, i) => {
          const p = S.answers[i];
          return `
          <div class="g-card g-quick">
            <div class="g-quick-head">
              <div class="g-quick-badge">Quick-fire ${i + 1}</div>
              <div class="g-quick-t">${esc(c.title)}</div>
            </div>
            <p class="g-quick-s">${esc(c.scenario)}</p>
            ${showHints && p === undefined ? `<div class="g-quick-hint">Hint: ${esc(c.hint)}</div>` : ""}
            <div class="g-opts">
              ${c.options.map((o, j) => optionHTML(o, j, p, "quick-pick", i)).join("")}
            </div>
          </div>`;
        }).join("")}
      </div>

      <button class="btn btn-primary" ${act("go-skills")}>Next: the skill map →</button>`;
    },

    skills: () => `
      <div class="g-intro">
        <div class="g-kicker">Chapter 5 · The skill map</div>
        <h1 class="g-chapter-h1">Six skills. All learnable. None require permission.</h1>
        <p>You don't need a title to practice any of these. Each card tells you exactly how to start — today, for free.</p>
      </div>
      <div class="g-grid g-grid-300" style="margin-bottom:36px;">
        ${CONTENT.skills.map((sk) => `
          <div class="g-card g-skill">
            <div class="g-skill-n">${esc(sk.name)}</div>
            <div class="g-skill-w">${esc(sk.why)}</div>
            <div class="g-skill-how">
              <div class="g-label g-label-2">How to learn it</div>
              <div>${esc(sk.how)}</div>
            </div>
          </div>`).join("")}
      </div>
      <div class="g-dark g-meta">
        <div class="g-meta-t">The meta-skill: build, write, ship.</div>
        <div class="g-meta-b">Reading about PM won't make you one. Pick any product you use, write a one-page teardown of what you'd improve and why, and show it to someone. Do that ten times and you'll have more real practice than most applicants.</div>
      </div>
      <button class="btn btn-primary" ${act("go-breakin")}>Final chapter: breaking in →</button>`,

    breakin: () => `
      <div class="g-intro">
        <div class="g-kicker">Chapter 6 · Breaking in</div>
        <h1 class="g-chapter-h1">Nobody starts as a PM. Everybody starts as something.</h1>
        <p>Engineers, teachers, analysts, baristas — PMs come from everywhere. What they share is proof they can think like one. Here's how to build that proof.</p>
      </div>

      <h2 class="g-h2-sm">Make your resume tell PM stories</h2>
      <div class="g-grid g-grid-240" style="gap:14px;margin-bottom:48px;">
        ${CONTENT.resumeTips.map((r) => `
          <div class="g-card g-tip">
            <div class="g-tip-t">${esc(r.title)}</div>
            <div class="g-tip-b">${esc(r.body)}</div>
          </div>`).join("")}
      </div>

      <h2 class="g-h2-sm" style="margin-bottom:6px;">The four interviews you'll face</h2>
      <p class="g-h2-lede" style="margin-bottom:16px;">Almost every PM loop is some mix of these. Each has a learnable structure.</p>
      <div class="g-ivs">
        ${CONTENT.interviews.map((iv) => `
          <div class="g-card g-iv">
            <div>
              <div class="g-iv-n">${esc(iv.name)}</div>
              <div class="g-iv-f">${esc(iv.framework)}</div>
            </div>
            <div>
              <div class="g-iv-q">"${esc(iv.question)}"</div>
              <div class="g-iv-a">${esc(iv.approach)}</div>
            </div>
          </div>`).join("")}
      </div>

      <h2 class="g-h2-sm">A short shelf, not a long list</h2>
      <div class="g-grid" style="grid-template-columns:repeat(auto-fit,minmax(260px,1fr));margin-bottom:48px;">
        ${CONTENT.resourceCols.map((col) => `
          <div class="g-card g-shelf">
            <div class="g-label g-label-2">${esc(col.label)}</div>
            <div class="g-shelf-items">
              ${col.items.map((it) => `
                <div><div class="g-shelf-n">${esc(it.name)}</div><div class="g-shelf-note">${esc(it.note)}</div></div>`).join("")}
            </div>
          </div>`).join("")}
      </div>

      <div class="g-card g-plan">
        <button class="g-plan-head" ${act("plan")} aria-expanded="${S.planOpen}">
          <div style="flex:1;">
            <div class="g-plan-t">Want a plan? Here's 30 days.</div>
            <div class="g-plan-s">Entirely optional — the teardowns above matter more than any schedule.</div>
          </div>
          <div class="g-chevron">${S.planOpen ? "−" : "+"}</div>
        </button>
        ${S.planOpen ? `
        <div class="g-plan-body">
          ${CONTENT.plan.map((wk) => `
            <div class="g-week">
              <div class="g-label">${esc(wk.week)}</div>
              <div class="g-week-t">${esc(wk.title)}</div>
              <div class="g-week-b">${esc(wk.body)}</div>
            </div>`).join("")}
        </div>` : ""}
      </div>

      <div class="g-closing">
        <p>The best PMs weren't anointed. They just started acting like one before anyone gave them the title — and eventually, someone did.</p>
        <button class="btn btn-secondary" style="margin-top:10px;" ${act("go-home")}>← Back to the start</button>
      </div>`,
  };

  // ── "what does this mean?" ─────────────────────────────────────────────────
  // Select any word (or double-tap it) anywhere in the guide and a chip offers
  // to explain it; the popover also takes a typed question. Most lookups are
  // answered from a curated glossary server-side, so they're instant and cost
  // nothing — the model is only reached for words we haven't written down.
  const ask = (() => {
    let chip = null, pop = null, lastTerm = "";

    const close = () => {
      if (chip) { chip.remove(); chip = null; }
      if (pop) { pop.remove(); pop = null; }
    };
    const hideChip = () => { if (chip) { chip.remove(); chip = null; } };

    // The sentence around the selection, so the model can tell "ship a
    // feature" from "ship at sea". Cheap to send, and it stays server-capped.
    function sentenceAround(sel) {
      try {
        const whole = sel.anchorNode && sel.anchorNode.textContent;
        if (!whole) return "";
        return whole.trim().slice(0, 300);
      } catch { return ""; }
    }

    function place(node, rect) {
      // Positioned in page space so the popover scrolls with the text.
      node.style.left = (rect.left + rect.width / 2 + window.scrollX) + "px";
      node.style.top = (rect.bottom + window.scrollY + 8) + "px";
    }

    function open(term, context, rect) {
      close();
      lastTerm = term;
      pop = document.createElement("div");
      pop.className = "g-pop";
      pop.innerHTML = `
        <div class="g-pop-head">
          <div class="g-pop-term">${esc(term)}</div>
          <button class="g-pop-x" data-x aria-label="Close">×</button>
        </div>
        <div class="g-pop-body" data-body>Looking that up…</div>
        <div class="g-pop-hint">
          <input type="text" data-q placeholder="Ask about another word…"
                 style="width:100%;padding:7px 12px;border-radius:999px;border:1px solid var(--color-divider);font:inherit;font-size:13.5px;background:var(--color-bg);color:var(--color-text);" />
        </div>`;
      document.body.appendChild(pop);
      place(pop, rect);
      pop.querySelector("[data-x]").onclick = close;
      const q = pop.querySelector("[data-q]");
      q.addEventListener("keydown", (e) => {
        if (e.key !== "Enter") return;
        const v = q.value.trim();
        if (v) { open(v, "", rect); }
      });
      fetchExplain(term, context, rect);
    }

    async function fetchExplain(term, context, rect) {
      let d = null;
      try {
        const r = await fetch("/api/guide/explain", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ term, context }),
        });
        d = await r.json();
      } catch { d = null; }
      if (!pop || lastTerm !== term) return; // a newer question overtook this one
      const body = pop.querySelector("[data-body]");
      if (!d || !d.ok) {
        body.textContent = (d && d.error) || "Couldn't look that one up — try again.";
      } else {
        body.innerHTML = esc(d.plain).replace(/\n+/g, "<br>") +
          (d.example ? `<div class="g-pop-eg"><b>For example</b>${esc(d.example)}</div>` : "");
        track("term_explained", { term: term.slice(0, 40), source: d.source });
      }
      place(pop, rect);
    }

    // Offer the chip whenever there's a real selection inside the guide.
    document.addEventListener("mouseup", onSelect);
    document.addEventListener("touchend", onSelect);

    function onSelect(e) {
      if (pop && pop.contains(e.target)) return;
      setTimeout(() => {
        const sel = window.getSelection();
        const text = sel ? String(sel).trim() : "";
        // A phrase is fine; a paragraph isn't what this is for.
        if (!text || text.length > 60 || text.split(/\s+/).length > 6) return hideChip();
        const main = el("main");
        if (!main || !sel.anchorNode || !main.contains(sel.anchorNode)) return hideChip();
        const rect = sel.getRangeAt(0).getBoundingClientRect();
        if (!rect.width && !rect.height) return hideChip();
        hideChip();
        chip = document.createElement("button");
        chip.className = "g-ask";
        chip.textContent = `What does "${text.length > 22 ? text.slice(0, 22) + "…" : text}" mean?`;
        chip.onclick = () => open(text, sentenceAround(sel), rect);
        document.body.appendChild(chip);
        place(chip, rect);
      }, 0);
    }

    document.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
    document.addEventListener("mousedown", (e) => {
      if (pop && !pop.contains(e.target) && !(chip && chip.contains(e.target))) close();
    });

    return { open, close };
  })();

  // ── render ────────────────────────────────────────────────────────────────

  function render() {
    const main = el("main");
    main.className = "g-main" + (S.screen === "home" ? " is-home" : "");
    main.setAttribute("data-screen", S.screen);
    main.innerHTML = screens[S.screen]();

    el("nav").innerHTML = SCREENS.map(([k, label]) => {
      const cls = k === S.screen ? " is-active" : S.visited[k] ? " is-visited" : "";
      return `<button class="g-tab${cls}" ${act("nav")} data-screen="${k}"
                ${k === S.screen ? 'aria-current="page"' : ""}>${label}</button>`;
    }).join("");

    el("progress").textContent = Object.keys(S.visited).length + "/7 explored";
  }

  // One delegated handler for the whole page. `data-act` names the intent.
  const ACTIONS = {
    nav: (e) => go(e.target.closest("[data-screen]").dataset.screen),
    "go-home": () => go("home"),
    "go-role": () => go("role"),
    "go-types": () => go("types"),
    "go-decisions": () => go("decisions"),
    "go-cases": () => go("cases"),
    "go-skills": () => go("skills"),
    "go-breakin": () => go("breakin"),
    "home-card": (e, i) => go(CONTENT.homeCards[i].go),
    type: (e, i) => {
      set({ selectedType: i });
      track("type_selected", { type: CONTENT.pmTypes[i].name });
    },
    story: (e, i) => {
      const open = S.expandedStory !== i;
      set({ expandedStory: open ? i : -1 });
      if (open) track("story_opened", { story: CONTENT.stories[i].title });
    },
    "round-pick": (e, i, j) => {
      S.picks[i] = j;
      set({});
      track("round_answered", { round: i + 1, verdict: CONTENT.rounds[i].options[j].verdict });
    },
    continue: () => {
      const next = S.round + 1;
      set({ round: next });
      if (next >= 6) {
        const tally = { best: 0, ok: 0, trap: 0 };
        CONTENT.rounds.forEach((r, i) => {
          const o = r.options[S.picks[i]];
          if (o) tally[o.verdict]++;
        });
        track("case_completed", tally);
      }
    },
    reveal: () => {
      set({ reveal: !S.reveal });
      if (S.reveal) track("ideal_run_revealed");
    },
    restart: () => {
      set({ round: 0, picks: {}, reveal: false });
      track("case_restarted");
    },
    "quick-pick": (e, i, j) => {
      S.answers[i] = j;
      set({});
      track("quickfire_answered", { quickfire: i + 1, verdict: CONTENT.quick[i].options[j].verdict });
    },
    plan: () => {
      set({ planOpen: !S.planOpen });
      if (S.planOpen) track("plan_opened");
    },
  };

  document.addEventListener("click", (e) => {
    const node = e.target.closest("[data-act]");
    if (!node) return;
    const fn = ACTIONS[node.dataset.act];
    if (!fn) return;
    const i = node.dataset.i === undefined ? undefined : Number(node.dataset.i);
    const j = node.dataset.j === undefined ? undefined : Number(node.dataset.j);
    fn(e, i, j);
  });

  // Deep links (/guide#skills) and the browser back button both drive `screen`.
  const fromHash = () => {
    const k = location.hash.replace(/^#/, "");
    return SCREENS.some(([s]) => s === k) ? k : "home";
  };
  window.addEventListener("hashchange", () => go(fromHash(), { fromHash: true }));

  go(fromHash(), { fromHash: true });
})();
