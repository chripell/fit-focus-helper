from astropy.stats import sigma_clipped_stats
from photutils import DAOStarFinder, IRAFStarFinder
import numpy as np


class Focuser:

    def __init__(
            self, fwhm=3.0, threshold_stds=3., algo='iraf', n_stars=100):
        self.sources = None
        self.n = 0
        self.mean = {}
        self.fwhm = fwhm
        self.threshold_stds = threshold_stds
        self.n_stars = n_stars
        self.algo = algo
        if self.algo == 'dao':
            self.odata = ("sharpness", "roundness1", "roundness2")
        else:
            self.odata = ("sharpness",)

    def evaluate(self, data):
        mean, median, std = sigma_clipped_stats(data, sigma=3.0, maxiters=5)
        self.back = median
        self.back_std = std
        if self.algo == 'dao':
            finder = DAOStarFinder(
                fwhm=self.fwhm, threshold=self.threshold_stds*std,
                brightest=self.n_stars)
        else:
            finder = IRAFStarFinder(
                fwhm=self.fwhm, threshold=self.threshold_stds*std,
                brightest=self.n_stars, minsep_fwhm=5)
        self.sources = finder(data - median)
        if self.sources is None:
            return
        for col in self.sources.colnames:
            self.sources[col].info.format = "%.8g"
        if self.num() > 0:
            for p in self.odata:
                self.mean[p] = np.absolute(self.sources.field(p)).mean()
        return self.sources

    def draw(self, cr, par, scale=1.0, radius=10, show_text=False):
        if self.sources is None:
            return
        if par not in self.odata:
            par = self.odata[0]
        mean = self.mean[par]
        m_pi = 2 * np.pi
        cr.set_font_size(15)
        for i in self.sources:
            if abs(i[par]) >= mean:
                cr.set_source_rgb(0, 1.0, 0)
            else:
                cr.set_source_rgb(1.0, 0, 0)
            x = i["xcentroid"] / scale
            y = i["ycentroid"] / scale
            cr.arc(x, y, radius, 0, m_pi)
            cr.stroke()
            if not show_text:
                continue
            cr.move_to(x + radius + 2, y + radius + 2)
            cr.show_text("%.2f" % i[par])
            cr.stroke()

    def num(self):
        if self.sources is not None:
            return len(self.sources)
        return 0
