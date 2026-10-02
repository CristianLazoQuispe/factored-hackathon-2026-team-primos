// Showing a reply at the pace of the voice that reads it. Kokoro gives no word times, so they are
// estimated: a line's audio lasts a known time and each word takes a share of it.

// How long each kind of character takes to say, relative to a letter. Fitted on 15 real reply
// lines timed with Whisper: word starts land within 0.1 s on average, against 0.6 s (and up to
// 2.6 s) when every character counts the same.
const DIGIT = 8; // "$6,662.27" takes about 2.5 s
const ACRONYM = 5; // "USD" is spelled out
const PAUSE = 2; // the breath after , . : ; ? ! )

function weight(word: string) {
  const letters = word.match(/\p{L}/gu)?.length ?? 0;
  const digits = word.match(/\d/g)?.length ?? 0;
  const acronym = letters >= 2 && word === word.toUpperCase();
  const pause = /[,.:;?!)]$/.test(word.trimEnd()) ? PAUSE : 0;
  return letters * (acronym ? ACRONYM : 1) + digits * DIGIT + pause;
}

// How many characters of `line` to show once `fraction` of its audio has played: every word
// whose turn has started. Markdown symbols weigh nothing, so a list mark comes with its first word.
export function revealed(line: string, fraction: number) {
  const words = [...line.matchAll(/\S+\s*/g)];
  const total = words.reduce((sum, word) => sum + weight(word[0]), 0);
  let before = 0;
  let end = 0;
  for (const word of words) {
    if (before > fraction * total) break;
    end = word.index + word[0].length;
    before += weight(word[0]);
  }
  return fraction >= 1 ? line.length : end;
}

// The first `shown` characters of a markdown text, with the bold or italic that the cut left
// open closed again, so no loose asterisks are ever on screen.
export function visible(text: string, shown: number) {
  const cut = text.slice(0, shown);
  const marks = cut.replace(/^\s*\*\s/gm, ""); // a `*` that starts a list item is not emphasis
  const bold = (marks.match(/\*\*/g)?.length ?? 0) % 2 === 1;
  const italic = (marks.replace(/\*\*/g, "").match(/\*/g)?.length ?? 0) % 2 === 1;
  return bold || italic ? `${cut.trimEnd()}${italic ? "*" : ""}${bold ? "**" : ""}` : cut;
}
