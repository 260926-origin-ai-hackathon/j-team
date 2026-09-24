"""建物の遮音の計算（python-acoustics の acoustics/building.py から必要な関数だけを取り込んだもの）

取り込み元: https://github.com/python-acoustics/python-acoustics  acoustics/building.py
（rw_curve / rw / rw_ctr / mass_law。コードは変えず、コメントだけ日本語で足した）

Copyright (c) 2013, Python Acoustics
All rights reserved.

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright notice, this
  list of conditions and the following disclaimer in the documentation and/or
  other materials provided with the distribution.

* Neither the name of the {organization} nor the names of its
  contributors may be used to endorse or promote products derived from
  this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""
import numpy as np

# 1/3オクターブの中心周波数（100Hz〜3.15kHz、ISO 717-1 の評価に使う16帯域）
THIRD_OCTAVES = np.array([100, 125, 160, 200, 250, 315, 400, 500, 630, 800,
                          1000, 1250, 1600, 2000, 2500, 3150], dtype=float)


def rw_curve(tl):
    """ISO 717-1 の基準曲線を、透過損失 tl（1/3オクターブ16帯域）に合わせて動かしたもの。"""
    ref_curve = np.array([0, 3, 6, 9, 12, 15, 18, 19, 20, 21, 22, 23, 23, 23, 23, 23])
    residuals = 0
    while residuals > -32:
        ref_curve += 1
        diff = tl - ref_curve
        residuals = np.sum(np.clip(diff, np.min(diff), 0))
    ref_curve -= 1
    return ref_curve


def rw(tl):
    """重み付き音響透過損失 Rw（500Hz での基準曲線の値）。"""
    return rw_curve(tl)[7]


def rw_ctr(tl):
    """道路交通騒音のスペクトルで重み付けした Rw + Ctr。車の音に対する遮音はこちらで見る。"""
    k_tr = np.array([-20, -20, -18, -16, -15, -14, -13, -12, -11, -9, -8, -9, -10, -11, -13, -15])
    a_tr = -10 * np.log10(np.sum(10**((k_tr - tl) / 10)))
    return a_tr


def mass_law(freq, vol_density, thickness, theta=0, c=343, rho0=1.225):
    """質量則による透過損失。壁が重い（密度×厚さが大きい）ほど音を通しにくい。"""
    rad_freq = 2.0 * np.pi * freq
    surface_density = vol_density * thickness
    theta_rad = np.deg2rad(theta)
    a = rad_freq * surface_density * np.cos(theta_rad) / (2 * rho0 * c)
    tl_theta = 10 * np.log10(1 + a**2)
    return tl_theta
