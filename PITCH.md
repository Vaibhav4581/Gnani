# Bacha Hua Khana: say it once, and leftover food reaches people who need it

Voice-first surplus food rescue, built on Gnani AI (Prisma v2.5 and Timbre v2.5), for the Great
Indian AI Internship Challenge.
**[Demo video](https://drive.google.com/file/d/12cUXhsOdToK_45wKHgcAz0bC6n48m_FJ/view?usp=drive_link)** ·
**[Code](https://github.com/Vaibhav4581/Gnani)** · [One-page PDF](PITCH.pdf)

## The problem

Mess kitchens, hostels, canteens and weddings throw away cooked food every evening, while shelters a
few kilometres away go short. Rescue fails at the first step: the person with the food has wet hands,
a loud kitchen and no time to fill in a form, and the volunteer who could carry it may not read English.

## The solution

A three-way chain that runs entirely by voice, with each person in their own language (Hindi,
Malayalam, Kannada or English):

1. **The shelter asks.** *"Aaj raat 80 logon ke liye khana chahiye."* The request is read back and confirmed.
2. **The kitchen reports.** One tap: *"Pachaas plate biryani bachi hai, do baje bani thi, Kakkanad se."*
   The app reads it back, fixes only what is corrected and asks for anything missing. It never acts on a guess.
3. **Safety by voice.** Two questions: is it veg, and is it covered and clean? Uncovered food goes nowhere.
4. **Matching.** The food goes to a shelter whose request it fits (veg-only respected, arriving before it
   is needed and within the food's 4-hour window), or else to a partner community-kitchen drop point.
5. **The volunteer call.** The best-placed volunteer with room for the load gets a call-style alert in
   their language. A "no", or no answer, rings the next one.
6. **Delivery confirmed by voice.** The shelter says *"haan, aa gaya"*. A live board and a shareable
   impact card close the loop.

After every question the mic opens by itself and stops on silence, so nobody has to keep tapping the screen.

## Built on Gnani AI

- **Prisma v2.5 speech-to-text** understands code-mixed Hinglish and Manglish as well as native
  scripts. On 18 test clips in four languages, 16 were fully right in quiet, noisy and phone-line
  (8 kHz) audio alike, and every yes/no answer was understood. Live transcription averaged about 2 s.
- **Timbre v2.5 text-to-speech** speaks every read-back, question and alert. Phrases are cached, so a
  repeat costs no credits.
- A mock mode runs the whole app without spending credits, and 831 automated tests cover it.

## Why it can work

- Voice removes the typing barrier for kitchen staff and volunteers.
- Everyone hears and reads their own language and script.
- Read-backs and safety questions make it trustworthy, not just fast.
- It is a single service that is simple to run, and the same flow can move to phone calls with Gnani.

## Next steps

A pilot with two Kochi hostel messes and one shelter; real phone calls; testing with real accents and
kitchen noise; and verified partner organisations for food safety.

*Prototype on synthetic data; no real phone calls yet.*
