---
description: Break something on purpose and show the test catching it — proving the test would actually fail if the feature regressed
---

# /prove-it <feature, test, or AC id>

A passing test proves the test passes. It does not prove the test would **fail** if the
feature broke. Those are different claims, and only the second one is worth anything.

This command establishes the second one, and takes about a minute.

## Steps

1. **Name the guarantee.** What, exactly, is this test or check supposed to catch? One
   sentence. If you can't write it, that is the finding — report it and stop.
2. **Name the break.** The smallest realistic change that would violate that guarantee. It
   must be a plausible regression — a value, a condition, a prop, a padding — not deleting
   the whole function. Anything catches a deleted function.
3. **Make the break.** In the working tree.
4. **Run the check. Show the actual failure output**, quoted, not summarised.
5. **Revert the break.**
6. **Run the check again. Show it green**, so the revert is proven clean and no residue
   is left behind.

## Report

| | |
|---|---|
| Guarantee | |
| Break introduced | |
| Result | **CAUGHT** / **NOT CAUGHT** |
| Failure output | (quoted) |
| Reverted and green | yes / no |

## If the break was NOT caught

Do not quietly fix the test and re-run. **Stop and report it.** A test that passes through a
real regression is worse than no test, because it is actively spending the owner's trust.
Say what the test actually asserts, versus what everyone assumed it asserted.

## Notes

- Never leave the break in the tree. Step 6 is not optional.
- Use this on anything the owner is being asked to trust: a new test suite, a visual
  baseline, a guardrail, a validation rule. It is the cheapest possible substitute for
  reading the implementation.
