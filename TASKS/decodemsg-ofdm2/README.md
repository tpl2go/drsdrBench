# OFDM decoding challenge

## signal recording details
- signal sampling rate = 48khz
- signal has freq offset, use the single frequency tone for sync and freq offset measure
- no resampling needed for decoding

## Signal structure

### burst structure
- burst 1
  - single frequency tone (1024 samples)
- gap (100 samples)
- burst 2
  - pilot block cyclic prefix (96 samples)
  - pilot block (1024 samples)
  - data block cyclic prefix (96 samples)
  - data block (1024 samples)

### OFDM structure
- the ofdm symbol is 1024 samples and 1024 fft size
- the ofdm symbol freq bins are 128zeros 768samples 128zeros = 1024 samples total

### bits to text mapping
- bpsk mod
  - bit 0 = 180 degrees 
  - bit 1 = 0 degrees
- data block phase is related to the pilot block
- msb is sent first
- each char is 8bits long

### output hint
- text is 96 char or 768 bits
- text has amazon gift card
- first 8 bits are:  01110011

