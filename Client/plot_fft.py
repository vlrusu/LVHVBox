

import numpy as np

from scipy.fft import fft, fftfreq, ifft

import matplotlib.pyplot as plt

 

# Open file and read data into numpy array

data = np.loadtxt('full_currents_1705048947.txt')

 

# Separate time column from signal column

time = [(1./235.85E3) * i for i in range(len(data))]

#time = (1./109.7E3) * data[:, 0]

#time = (1e-6*243057./8192.) * data[:, 0]

signal = data

signal = signal - signal.mean()

 

print(time[1]-time[0])

# Calculate FFT of signal column

fft_signal = ifft(signal)

 

# Calculate the frequency values for each FFT coefficient

freq = fftfreq(len(signal), d=time[1]-time[0])

 

# Plot the FFT results


plt.plot(freq, abs(fft_signal)**2)
plt.xlim((-100,120000))

plt.xlabel('Frequency (Hz)')

plt.ylabel('Amplitude Squared')

plt.title("Power distribution in frequency domain")

plt.show()