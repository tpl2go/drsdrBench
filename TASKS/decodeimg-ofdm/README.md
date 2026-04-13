# ofdm tv challenge


## Recording Details
- sampling rate = 48khz
- I/Q wave file

## Signal Structure
signal starts with a LFM chirp signal.

The chirp signal details:

```matlab
fs = 48e3;
dt = 1/fs;
pw = 100e-3;
bw = 12e3;
slope = bw/pw;
t = [dt:dt:pw];
t = t - pw/2;
lfm = exp(1i * pi *slope * t.^2);
```

A matched filter is needed to find this chirp signal .

After chirp signal is ofdm tv signal. 
This ofdm signal has  480*1024 samples in total

## Output Hint
- reshape these samples into a 480 x 1024 matrix
- then take fft of each row in the matrix
- do a fftshift of each row in the matrix
- let's call this matrix X
- the first line in the image is `angle(X(2,:)./X(1,:))`
- the second line in the image is `angle(X(3,:)./X(2,:))`
- and so on
- the image contains a amazon gift card.

