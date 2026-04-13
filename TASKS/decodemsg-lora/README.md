# LoRa Decode

## Recording Details
- IQ data in wav file
- total samples in file:  364800 samples

## Signal Structure

```matlab
fs = 48e3;
dt = 1/fs;
pw = 50e-3;
bw = 12e3;
slope = bw/pw;
t = [dt:dt:pw];
t = t - pw/2;
x1 = pi * slope * t.^2  +        2 * pi *1e3 *t;
x2 = pi * slope * t.^2  -        2 * pi* 1e3 * t;
bit1 = exp(1i*x1);
bit0 = exp(1i*x2);
```

- samples per symbol = 2400
- signal is under noise

to decode signal,
- multiply symbol by  exp( -1i * pi * slope * t.^2 ) 
- then fft the product, to detect tone:    -1khz or 1khz  


## Output hint
- number of char:  19
- each char is 8 bits
- number of bits:  152 bits
- first 8 bits:   01000001 ,   or char A
- text is amazon gift card


