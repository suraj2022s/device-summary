# Defects found and fixed

Only real defects are listed, in the order they were found, with the commit that fixed
them and the test that now guards them.

## 1. Response shape did not match the brief

- **Symptom:** the first draft nested the totals: `{"totals": {"accepted": 3, ...}, ...}`.
  The brief asks for "accepted and duplicate totals, an ordered error list" and, for
  empty input, "zero totals and empty lists", which describes a flat object.
- **Found by:** writing the brief's three tests before touching the draft; all five
  test cases failed on the shape.
- **Fix:** `02d80a0`. The response is `{accepted, duplicates, errors, devices}`.
- **Guarded by:** `tests/test_required.py`, which compares the empty-input result exactly.

## 2. Duplicate keys were checked before the line was known to be valid JSON

- **Symptom:** the draft raised an error from inside the JSON parser as soon as an object
  repeated a key. For `{"sequence": 1, "sequence": 2} trailing`, which is not valid
  JSON at all, it reported `INVALID_RECORD` instead of `BAD_JSON`.
- **Found by:** code review while restructuring the draft into decode, parse and
  validate steps.
- **Fix:** `02d80a0`. The parser marks the object and validation rejects it later, so
  syntax errors always win.
- **Guarded by:** `test_bad_json_is_reported_and_processing_continues[duplicate-key-and-broken-syntax]`.

## 3. An invisible character in the source, and a fix that did not happen

- **Symptom:** the byte order mark constant in `summary.py` was the raw, invisible U+FEFF
  character, which looks exactly like an empty string on screen. It worked, but nobody
  reading or editing the file could see it. Commit `02d80a0` said it had been replaced
  with an escape sequence; it had not. The AI editing tool had written the `\ufeff`
  escape to disk as the raw character. The same thing happened to a `\u2028` in a test.
- **Found by:** ruff (`RUF001`) flagged the raw U+2028 in `tests/test_lines.py`. A scan
  of every source file for non-ASCII characters then showed U+FEFF still in `summary.py`.
- **Fix:** `6e5375c`. The constant is `codecs.BOM_UTF8.decode("utf-8")` and the test
  value is `"D\N{LINE SEPARATOR}01"`, spellings that stay visible.
- **Guarded by:** `tests/test_source_hygiene.py` fails on any invisible or format
  character. It was checked by planting a BOM in a temporary file, which it caught.
- **It happened once more:** while this document was being written, the two escapes in
  the Symptom above were saved as raw characters too. A scan of all text files caught it,
  and the guard was widened from Python files to every text file in the repository
  (Markdown, TOML, YAML, the sample data and the Dockerfile).

## 4. Error reasons pointed at the wrong column

- **Symptom:** for the sample's truncated line, the reason said
  `Expecting ',' delimiter at column 1`; the real position is column 51.
- **Cause:** commit `47aa609` removed the stripping of `\n` and `\r\n` as redundant. That
  was true for choosing the error code, since JSON ignores surrounding whitespace, and
  the mutation check agreed. But with the newline left in, Python's parser reports an
  error at the end of a line as "line 2, column 1". No test looked at the column, so
  neither the tests nor the mutation check could notice.
- **Found by:** running the CLI on the sample and reading the actual output.
- **Fix:** `6e5375c`. Line endings are stripped again.
- **Guarded by:** `test_malformed_json_reason_points_at_the_real_column` for LF and CRLF
  files. It fails without the fix (checked by stashing it). `scripts/check_mutations.py`
  now includes this mutation too.
- **Lesson:** a mutation check only proves what the tests look at. Checking the real
  output caught what the automated checks could not.

## 5. Design corrections made before the code was committed

- **503 changed to 500 for an unreadable file.** The draft API returned 503. RFC 9110
  defines 503 as "temporary overload or scheduled maintenance"; a missing data file is
  an "unexpected condition", which is 500. The body also moved to RFC 9457 problem
  details.
- **Deprecated test client dependency.** Starlette 1.7 warns that using `httpx` with its
  `TestClient` is deprecated in favour of `httpx2`, Pydantic's maintained fork. The dev
  dependency was switched, and pytest now treats every warning as an error so this kind
  of drift fails the build (`96590bd`).

## 6. A test that only passed on some platforms

- **Symptom:** on the first CI run, 9 of 10 jobs passed, but Ubuntu with Python 3.14.7
  failed. A test fed 100,000 levels of nested brackets and expected `BAD_JSON` ("JSON is
  nested too deeply"); that platform returned `INVALID_RECORD`. Coverage also dropped
  below 100%, because the `RecursionError` handler never ran there.
- **Cause:** the test assumed that depth always makes Python's parser raise
  `RecursionError`. How deep the parser can go depends on the Python version and the
  platform's stack size. On Windows it raises; on Linux with Python 3.14 it parses the
  array, which is valid JSON but not an object, so `INVALID_RECORD` is the correct
  answer there. The code was right; the test and the README wording were not.
- **Found by:** the CI matrix (Ubuntu and Windows, Python 3.11 to 3.14). Local runs on
  Windows and WSL had passed.
- **Fix:** the `RecursionError` handling is now tested deterministically by simulating
  the error. Real deep nesting is tested only for what holds everywhere: the line is
  rejected with one of the two codes and processing continues. The README describes the
  platform dependence.

## 7. "at at" in an error reason

- **Symptom:** for a line cut off in the middle of a string, the reason read
  `malformed JSON: Unterminated string starting at at column 21`.
- **Cause:** some of Python's JSON error messages already end in "at" (they are meant to
  be followed by a position), and the reason appended " at column N" after them.
- **Found by:** running the CLI on a hand-written example file while explaining the
  project; no existing test used an unterminated string.
- **Fix:** a trailing " at" is dropped from Python's message before the column is added,
  so the reason reads `Unterminated string starting at column 21`.
- **Guarded by:** `test_malformed_json_reason_does_not_repeat_at`, which fails without
  the fix.
