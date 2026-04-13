# FSK decoding challenge

## signal recording details
- signal sampling rate = 48khz
- signal uses FSK modulation
- no resampling needed for decoding

## Signal structure

### bit structure
- bits per second = 1200
- 40 samples per bit
- file has 528 bits total
- ascii text, each char is 8bits
- msb is sent first

### tone mapping
- bit 0 = 1200 hz tone, 40 samples long
- bit 1 = 2400 hz tone, 40 samples long

### output hint
- decode the text and get the amazon claim code
- first ascii char in the wav file is: `t`
- first ascii char is 116 dec or 01110100 in binary

