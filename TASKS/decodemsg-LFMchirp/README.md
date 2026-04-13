# LFM Chirp Decode

## Recording details
sampling rate = 48khz

## Signal Structure

bits are defined by chirps

chirp details in matlab pseudocode:
```
pw = 200msec
bw = 12khz
slope = bw/pw
dt = 1/fs
t = [dt:dt:pw]
t = t - pw/2
bit1 = exp(1i * pi *slope *t.^2)
bit0 = exp(-1i *pi *slope *t.^2)
```

the signal is in noise, matched filter will be needed.
need to find start of signal

## Output hint
the first 8 bits are: 01100011
message has 216 bits,
Each character has 8 bits
27 characters in total

