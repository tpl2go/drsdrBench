# Chirp Text Message

## Recording Details
- IQ stored in wav file

## Signal Structure

chirp structure:

```matlab
fs = 48e3;
bw = 12e3;
pw = 50e-3;
slope = bw / pw;
ts = 1/fs;
t = [ts:ts:pw];
t = t - (pw/2);
bit1 = exp(1i * pi * slope* t.^2);
bit0 = exp(-1i * pi * slope* t.^2);
nsig = length(bit0);
txsig = zeros(Nbits,nsig);
```

samples per symbol = 2400



to make matched filter weights

```matlab
bit1detect = conj( bit1(end:-1:1));
bit0detect = conj( bit0(end:-1:1));
```

then use filter of `fftfilt` to run matched filter for bit0 and for bit1

```matlab
d1 = fftfilt(bit1detect,inputsig);
d0 = fftfilt(bit0detect,inputsig);
```

peaks at inputsig(2400:2400:end)
whatever sig is greater, shows a bit 0 or a bit 1

msb is sent first

## Output hint
- get bits back to text.
- number of bits = 144
- each char is 8 bits
- text message is a amazon claim code
