# 2D-FFT-I-Q-IMAGE

## Signal Structure

signal starts with a preamble LFM chirp defined below

```matlab
fs = 48e3;
pw = 100e-3;
dt = 1/fs;
bw = 12e3;
t = [dt:dt:pw];
t = t - pw/2;
slope = bw/pw;
lfm = exp( 1i *pi* slope *t.^2 );
```

after the chirp is the signal to be decoded

## Output Hint
- Form a 1024 x 1024 matrix
- Use 2D FFT
- image contains an amazon gift card code



