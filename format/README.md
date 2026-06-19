# Order of events

1. did_fa13 is data for the latest event.
2. did_fa14 is data for the second latest event.
3. did_fa15 is data for the third latest event.


# Conversion rules

A raw value can be converted using the following rules.

1. Search the value from the "Value table" column. If found, the matched label
   is the result.
2. If not found, convert the value as described in the "Conversion" column,
   where E and N are:

* E: Converted value
* N: Raw value (unsigned integer)

## Value table column

Entries are separated by `;`. Each entry is `<hex_key>:<label>`.

Example: `0xFE:Invalid;0xFF:N/A` (single-byte signal) or
`0xFFFE:Invalid;0xFFFF:N/A` (two-byte signal — the key matches the aggregated
multi-byte raw value).

`N/A` in this column means there is no value table for that row.

## Conversion column

Possible values:

* **Linear formula** `E=N`, `E=N+K`, `E=N-K`, `E=N*K`, `E=N*K+K`, `E=N*K-K`
  where K is a real number. The reader applies the formula directly.
* **`Ascii`** — the raw byte is rendered as a printable ASCII character (or as
  `0xHH` if not printable).
* **`Not defined`** or **`N/A`** — there is no formula. Only a Value table
  match produces a physical value; otherwise the cell is left empty.
* **`Subsequent byte`** — this row is a continuation of the previous signal
  (see Multi-byte signals below).

## Multi-byte signals

A multi-byte signal is represented by **one leading row** (carrying the Name,
Unit, Value table, and Conversion) followed by **one or more continuation rows**
in which both "Value table" and "Conversion" contain `Subsequent byte`. The
continuation rows repeat the Name for human readability.

**Byte order: big-endian (Motorola).** The byte order is not specified by
GB39732 nor by ISO 15765; this tool fixes it to big-endian, following
automotive industry convention. The CSV does not encode byte order per signal.
