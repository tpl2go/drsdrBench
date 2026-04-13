# OFDM decoding challenge

## signal recording details
- signal sampling rate = 48khz
- signal has a freq offset, needs to be removed
- no resampling needed for decoding

## signal structure

### burst structure
- pulse (8192 samples)
- gap (1000 samples)
- pilot block cyclic prefix (512 samples)
- pilot block (3072 samples)
- data block cyclic prefix (512 samples)
- data block (3072 samples)

### OFDM structure
- fft size = 3072
- take fft of the pilot block and data block
- use fftshift after fft to center the spectrum
- spectrum layout = 512 guard bins, 2048 data bins, 512 guard bins

### bits to text mapping
- bpsk mod
  - bit 0 = 180 degrees
  - bit 1 = 0 degrees
- data block phase is related to the pilot block
- each char is 8 bits long
- number of chars = 256
- number of bits = 256 * 8

