# Audio OFDM

## Recording Details
- Sampling rate is 8kHz
- Hint: since audio and not i/q,  only half of the fft is needed.

## Signal Structure

- linear chirp from 300hz to 3kHz in 1s (8000 samples)
- dead time (512 samples)
- pilot block (8703 samples)
- data block (8703 samples)


data block phase is related to pilot block phase. Hint: 
- take fft of pilot block
- take fft of data block
- then   abs (  angle( fft_data ./ fft_pilot)  )

fft size = 8703
bits start at bin 129 
number of bits = 4096


## bits to symbol

- bit0 = 180 degrees
- bit1 = 0 degrees

## output hint

number of characters = 512
number of bits = 4096
each char is 8bits

message contains amazon gift card code.


