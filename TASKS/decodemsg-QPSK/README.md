# qpsk decoding challenge

## signal recording details
- signal sampling rate = 48khz
- qpsk iq wav file
- 40 samples per symbol
- 72 symbols total
- 2880 samples total
- signal has freq offset applied

## Signal structure

### frame structure
- qpsk symbol stream
- total payload = 18 char
- total payload = 144 bits
- no resampling needed for decoding

### qpsk structure
- each symbol encodes 2 bits
- bit pair to phase mapping:
  - `00` = 45 degrees
  - `01` = 135 degrees
  - `10` = -45 degrees
  - `11` = -135 degrees

### bits to text mapping
- each char is 8bits long
- first 8 bits of signal: `01000001`
- first 8 bits = char `A`

## output hint
- text string is amazon gift card code
- good luck
