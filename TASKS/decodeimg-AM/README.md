# AM-TV-Image-Decode

## Recording Details
- sampling rate = 48khz
- wav file is an IQ file

## Signal Structure
- AM Signal modulating a image not voice.

## Output Hint
- image is 800x800
- demod the am signal, first 800 samples are first line in image,  second 800 samples are second line in the image.
- total samples =  800 x 800