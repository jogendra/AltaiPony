import numpy as np
import pandas as pd
import datetime
import logging
import copy
import random
from scipy.stats import binned_statistic

LOG = logging.getLogger(__name__)

def inject_fake_flares(lc, mode='loglog', gapwindow=0.1, fakefreq=.25,
                       inject_before_detrending=False, d=False, seed=0,
                       **kwargs):

    '''
    Create a number of events, inject them in to data
    Use grid of amplitudes and durations, keep ampl in relative flux units
    Keep track of energy in Equiv Dur.
    Duration defined in minutes
    Amplitude defined multiples of the median error


    Parameters:
    -------------
    lc: FlareLightCurve
        contains info about flare start and stop in lc.flares
    mode : 'loglog', 'hawley2014' or 'rand'
        injection mode
    gapwindow : 0.1 or float

    fakefreq : .25 or float
        flares per day
    inject_before_detrending : True or bool
        By default, flares are injected before the light curve is detrended.
    d :

    seed :

    kwargs : dict
        Keyword arguments to pass to generate_fake_flare_distribution.

    Returns:
    ------------
    FlareLightCurve with fake flare signatures

    '''

    def _equivalent_duration(time, flux):
        '''
        Compute the Equivalent Duration of a fake flare.
        This is the area under the flare, in relative flux units.

        Parameters:
        -------------
        time : numpy array
            units of DAYS
        flux : numpy array
            relative flux units
        Return:
        ------------
        p : float
            equivalent duration of a single event in units of seconds
        '''
        x = time * 60.0 * 60.0 * 24.0
        integral = np.sum(np.diff(x) * flux[:-1])
        return integral


    LOG.debug(str() + '{} FakeFlares started'.format(datetime.datetime.now()))
    if inject_before_detrending == True:
        typ, typerr = 'flux', 'flux_err'
        LOG.debug('Injecting before detrending.')
    elif inject_before_detrending == False:
        typ, typerr = 'detrended_flux', 'detrended_flux_err'
        LOG.debug('Injecting after detrending.')
    fakeres = pd.DataFrame()
    fake_lc = copy.deepcopy(lc)
    fake_lc.__dict__[typ] = fake_lc.__dict__[typ]
    fake_lc.__dict__[typerr] = fake_lc.__dict__[typerr]
    nfakesum = int(np.rint(fakefreq * (lc.time.max() - lc.time.min())))
    t0_fake = np.zeros(nfakesum, dtype='float')
    ed_fake = np.zeros(nfakesum, dtype='float')
    dur_fake = np.zeros(nfakesum, dtype='float')
    ampl_fake = np.zeros(nfakesum, dtype='float')
    ckm = 0
    for (le,ri) in fake_lc.gaps:
        gap_fake_lc = fake_lc[le:ri]
        nfake = int(np.rint(fakefreq * (gap_fake_lc.time.max() - gap_fake_lc.time.min())))
        LOG.debug('Inject {} fake flares into a {} datapoint long array.'.format(nfake,ri-le))

        real_flares_in_gap = lc.flares[(lc.flares.istart >= le) & (lc.flares.istop <= ri)]
        error = gap_fake_lc.__dict__[typerr]
        flux = gap_fake_lc.__dict__[typ]
        time = gap_fake_lc.time
        mintime, maxtime = np.min(time), np.max(time)
        dtime = maxtime - mintime
        distribution  = generate_fake_flare_distribution(nfake, mode=mode, d=d,
                                                         seed=seed, **kwargs)
        dur_fake[ckm:ckm+nfake], ampl_fake[ckm:ckm+nfake] = distribution
        #loop over the numer of fake flares you want to generate
        for k in range(ckm, ckm+nfake):
    	    # generate random peak time, avoid known flares
    	    isok = False
    	    while isok is False:
    	        # choose a random peak time
    	        t0 = (mod_random(1, d=d, seed=seed*k) * dtime + mintime)[0]
    	        #t0 =  random.uniform(np.min(time),np.max(time))
                # Are there any real flares to deal with?
    	        if real_flares_in_gap.tstart.shape[0]>0:
                    # Are there any real flares happening at peak time?
                    # Fake flares should not overlap with real ones.
                    b = ( real_flares_in_gap[(t0 >= real_flares_in_gap.tstart) &
                                             (t0 <= real_flares_in_gap.tstop)].
                                            shape[0] )
                    if b == 0:
                        isok = True
    	        else:
                    isok = True
    	        t0_fake[k] = t0
    	        fl_flux = aflare(time, t0, dur_fake[k], ampl_fake[k])
    	        ed_fake[k] = _equivalent_duration(time, fl_flux)
            # inject flare in to light curve
    	    fake_lc.__dict__[typ][le:ri] = fake_lc.__dict__[typ][le:ri] + fl_flux*fake_lc.it_med[le:ri]
        ckm += nfake

    #error minimum is a safety net for the spline function if mode=3
    fake_lc.__dict__[typerr] = max( 1e-10, np.nanmedian( pd.Series(fake_lc.__dict__[typ]).
                                              rolling(3, center=True).
                                              std() ) )*np.ones_like(fake_lc.__dict__[typ])

    injected_events = {'duration_d' : dur_fake, 'amplitude' : ampl_fake,
                       'ed_inj' : ed_fake, 'peak_time' : t0_fake}
    fake_lc.fake_flares = fake_lc.fake_flares.append(pd.DataFrame(injected_events),
                                                     ignore_index=True,)
    #workaround
    fake_lc.fake_flares = fake_lc.fake_flares[fake_lc.fake_flares.peak_time != 0.]
    return fake_lc

def generate_fake_flare_distribution(nfake, ampl=[1e-4, 1e2], dur=[7e-3, 2],
                                     rat=[1e-3,1e4], mode='loglog', **kwargs ):

    '''
    Creates different distributions of fake flares to be injected into light curves.

    "uniform": Flares are distibuted evenly in duration and amplitude space.
    "hawley2014": Flares are distributed in a strip around a power law with
    exponent alpha, see Fig. 10 in Hawley et al. (2014).
    "loglog":

    Parameters
    -----------
    nfake: int
        Number of fake flares to be created.
    ampl: [1e-4, 1e2] or list of floats
        Amplitude range in relative flux units.
    dur: [10, 2e4] or list of floats
        Duration range in days.
    mode: 'loglog', 'hawley2014', 'uniform_ratio', or 'uniform'
        Distribution of fake flares in (duration, amplitude) space.
    kwargs : dict
        Keyword arguments to pass to mod_random

    Return
    -------
    dur_fake: durations of generated fake flares in days
    ampl_fake: amplitudes of generated fake flares in relative flux units
    '''
    def generate_range(n, tup, **kwargs):
        return (mod_random(n, **kwargs) * (tup[1] - tup[0]) + tup[0])

    if mode=='uniform':

        dur_fake =  generate_range(nfake, dur, **kwargs)
        ampl_fake = generate_range(nfake, ampl, **kwargs)

    elif mode=='uniform_ratio':
        dur_fake =  generate_range(nfake, dur, **kwargs)
        ampl_fake = generate_range(nfake, ampl, **kwargs)
        rat_fake = ampl_fake/dur_fake
        misfit = np.where(~((rat_fake < rat[1]) & (rat_fake > rat[0])))

        while len(misfit[0]) > 0:
            dur_fake_mf =  generate_range(len(misfit[0]), dur, **kwargs)
            ampl_fake_mf = generate_range(len(misfit[0]), ampl, **kwargs)
            dur_fake[misfit] = dur_fake_mf
            ampl_fake[misfit] = ampl_fake_mf
            rat_fake = ampl_fake/dur_fake
            misfit = np.where(~((rat_fake < rat[1]) & (rat_fake > rat[0])))

    elif mode=='hawley2014':

        c_range = np.array([np.log10(5) - 6., np.log10(5) - 4.])                #estimated from Fig. 10 in Hawley et al. (2014)
        alpha = 2                                                               #estimated from Fig. 10 in Hawley et al. (2014)
        ampl_H14 = [np.log10(i) for i in ampl]
        lnampl_fake = (mod_random(nfake, **kwargs) * (ampl_H14[1] - ampl_H14[0]) + ampl_H14[0])
        rand = mod_random(nfake, **kwargs)
        dur_max = (1./alpha) * (lnampl_fake - c_range[0])
        dur_min = (1./alpha) * (lnampl_fake - c_range[1])
        lndur_fake = np.array([rand[a] * (dur_max[a] - dur_min[a]) +
                              dur_min[a]
                              for a in range(nfake)])
        ampl_fake = np.power(np.full(nfake,10), lnampl_fake)
        dur_fake = np.power(np.full(nfake,10), lndur_fake)

    elif mode=='loglog':
        def generate_loglog(dur, ampl, nfake):

            lnampl = [np.log10(i) for i in ampl]
            lnampl_fake = generate_range(nfake, lnampl, **kwargs)
            lndur = [np.log10(i) for i in dur]
            lndur_fake = generate_range(nfake, lndur, **kwargs)
            return lndur_fake, lnampl_fake

        lndur_fake, lnampl_fake = generate_loglog(dur, ampl, nfake)
        rat_min, rat_max = [np.log10(i) for i in rat]
        lnrat_fake = lnampl_fake-lndur_fake
        misfit = np.where(~((lnrat_fake < rat_max) & (lnrat_fake > rat_min)))
        wait = 0

        while len(misfit[0]) > 0:
            wait+=1
            lndur_misfit, lnampl_misfit = generate_loglog(dur, ampl, len(misfit[0]))
            lndur_fake[misfit] = lndur_misfit
            lnampl_fake[misfit] = lnampl_misfit
            lnrat_fake = lnampl_fake-lndur_fake
            misfit = np.where(~((lnrat_fake < rat_max) & (lnrat_fake > rat_min)))
            if wait > 100:
                LOG.exception('Generating fake flares takes too long.'
                              'Reconsider dur_factor, ampl_factor, and ratio_factor.')
                raise ValueError

        ampl_fake = np.power(np.full(nfake,10), lnampl_fake)
        dur_fake = np.power(np.full(nfake,10), lndur_fake)

    return dur_fake, ampl_fake

def mod_random(x, d=False, seed=667):
    """
    Helper function that generates deterministic
    random numbers if needed for testing.

    Parameters
    -----------
    d : False or bool
        Flag to set if random numbers shall be deterministic.
    seed : 5 or int
        Sets the seed value for random number generator.
    """
    if d == True:
        np.random.seed(seed)
        return np.random.random(x)
    else:
        return np.random.random(x)

def aflare(t, tpeak, dur, ampl, upsample=False, uptime=10):
    '''
    The Analytic Flare Model evaluated for a single-peak (classical).
    Reference Davenport et al. (2014) http://arxiv.org/abs/1411.3723

    Use this function for fitting classical flares with most curve_fit
    tools.

    Note: this model assumes the flux before the flare is zero centered

    Parameters
    ----------
    t : 1-d array
        The time array to evaluate the flare over
    tpeak : float
        The time of the flare peak
    dur : float
        The duration of the flare
    ampl : float
        The amplitude of the flare
    upsample : bool
        If True up-sample the model flare to ensure more precise energies.
    uptime : float
        How many times to up-sample the data (Default is 10)

    Returns
    -------
    flare : 1-d array
        The flux of the flare model evaluated at each time
    '''
    _fr = [1.00000, 1.94053, -0.175084, -2.24588, -1.12498]
    _fd = [0.689008, -1.60053, 0.302963, -0.278318]

    fwhm = dur/2. # crude approximation for a triangle shape, should be even less

    if upsample:
        dt = np.nanmedian(np.diff(t))
        timeup = np.linspace(min(t)-dt, max(t)+dt, t.size * uptime)

        flareup = np.piecewise(timeup, [(timeup<= tpeak) * (timeup-tpeak)/fwhm > -1.,
                                        (timeup > tpeak)],
                                    [lambda x: (_fr[0]+                       # 0th order
                                                _fr[1]*((x-tpeak)/fwhm)+      # 1st order
                                                _fr[2]*((x-tpeak)/fwhm)**2.+  # 2nd order
                                                _fr[3]*((x-tpeak)/fwhm)**3.+  # 3rd order
                                                _fr[4]*((x-tpeak)/fwhm)**4. ),# 4th order
                                     lambda x: (_fd[0]*np.exp( ((x-tpeak)/fwhm)*_fd[1] ) +
                                                _fd[2]*np.exp( ((x-tpeak)/fwhm)*_fd[3] ))]
                                    ) * np.abs(ampl) # amplitude

        # and now downsample back to the original time...
        ## this way might be better, but makes assumption of uniform time bins
        # flare = np.nanmean(flareup.reshape(-1, uptime), axis=1)

        ## This way does linear interp. back to any input time grid
        # flare = np.interp(t, timeup, flareup)

        ## this was uses "binned statistic"
        downbins = np.concatenate((t-dt/2.,[max(t)+dt/2.]))
        flare,_,_ = binned_statistic(timeup, flareup, statistic='mean',
                                     bins=downbins)

    else:
        flare = np.piecewise(t, [(t<= tpeak) * (t-tpeak)/fwhm > -1.,
                                 (t > tpeak)],
                                [lambda x: (_fr[0]+                       # 0th order
                                            _fr[1]*((x-tpeak)/fwhm)+      # 1st order
                                            _fr[2]*((x-tpeak)/fwhm)**2.+  # 2nd order
                                            _fr[3]*((x-tpeak)/fwhm)**3.+  # 3rd order
                                            _fr[4]*((x-tpeak)/fwhm)**4. ),# 4th order
                                 lambda x: (_fd[0]*np.exp( ((x-tpeak)/fwhm)*_fd[1] ) +
                                            _fd[2]*np.exp( ((x-tpeak)/fwhm)*_fd[3] ))]
                                ) * np.abs(ampl) # amplitude

    return flare

def merge_fake_and_recovered_events(injs, recs):
    """
    Helper function that merges the DataFrames containing injected fake flares
    with the recovered events.

    Parameters
    -----------
    injs : DataFrame
        injected flares
    recs : DataFrame
        recovered flares

    Return
    ------
    DataFrame with both recovered and unrecovered events. The former contain
    additional info about recovered energy and captured datapoints.
    """
    recs['temp'] = 1
    injs['temp'] = 1
    merged = injs.merge(recs,how='outer')
    merged_recovered = merged[(merged.tstart < merged.peak_time) & (merged.tstop > merged.peak_time)]
    rest = injs[~injs.amplitude.isin(merged_recovered.amplitude.values)]
    merged_all = merged_recovered.append(rest).drop('temp',axis=1)
    return merged_all

def merge_complex_flares(data):
    """
    The injection procedure sometimes introduces complex flares. These are
    recovered multiple times, according to the number of simple flare signatures
    they consist of. Merge these by adopting common times, the maximum recovered
    equivalent duration and respective error. Add injected equivalent durations.

    Parameters
    -----------
    data : DataFrame
        Columns: ['amplitude', 'cstart', 'cstop', 'duration_d', 'ed_inj', 'ed_rec',
       'ed_rec_err', 'istart', 'istop', 'peak_time', 'tstart', 'tstop','ampl_rec']

    Return
    -------
    DataFrame with the same columns as the input but with complex flares merged
    together. A new 'complex' column contains the number of simple flares
    superimposed in a given event.
    """
    data = data.fillna(0)
    size = len(data.cstart[data.cstart == 0])
    maximum = data.cstop.max()+1e9
    data.loc[data.cstart == 0.,'cstart'] = np.arange(maximum,maximum+3*size,3)
    data.loc[data.cstop == 0.,'cstop'] = np.arange(maximum+1,maximum+3*size+1,3)
    g = data.groupby(['cstart','cstop'])
    data_wo_overlaps = pd.DataFrame(columns=np.append(data.columns.values,'complex'))
    for (start, stop), d in g:
        if d.shape[0] > 1:
            row = {
            'complex' : d.shape[0],
            'peak_time' : d.peak_time[d.amplitude.idxmax()],
            'amplitude' : d.amplitude.max(),
            'cstart' : d.cstart.min(),
            'cstop' : d.cstop.max(),
            'duration_d' : d.duration_d.max(),
            'ed_inj' : d.ed_inj.sum(),
            'ed_rec' : d.ed_rec.max(),
            'ed_rec_err' : d.ed_rec_err.max(),
            'istart' : d.istart.min(),
            'istop' : d.istop.max(),
            'tstart' : d.tstart.min(),
            'tstop' : d.tstop.max(),
            'ampl_rec' : d.ampl_rec.max()}
            e = pd.DataFrame(row, index=[0])
        else:
            x = d.to_dict()
            x['complex'] = 1
            e = pd.DataFrame(x)
        data_wo_overlaps = data_wo_overlaps.append(e, ignore_index=True)
    data_wo_overlaps.loc[data_wo_overlaps.cstart >= maximum,'cstart'] = np.zeros(size)
    data_wo_overlaps.loc[data_wo_overlaps.cstop >= maximum,'cstop'] = np.zeros(size)
    return data_wo_overlaps

def recovery_probability(data, bins=30, bintype='log', fixed_bins=False):
    """
    Calculate a look-up table that returns the recovery probability of a flare
    with some true equivalent duration in seconds.

    Parameters
    -----------
    data : DataFrame
        Table with columns that contain injected equivalent duration and info
        whether this flare was recovered or not.
    bins : 30 or int
        Size of look-up table.
    bintype : 'log' or 'lin'

    fixed_bins : False or bool

    Return
    ------
    DataFrame that gives bin edges in equivalent duration and the recovery
    probability in these bins.
    """
    data['rec'] = data.ed_rec.astype(bool).astype(float)
    if fixed_bins == False:
        num = min(int(np.rint(data.shape[0]/100)), bins + 1)
    else:
        num = bins + 1
    if bintype == 'log':
        bins = np.logspace(np.log10(data.ed_inj.min()*.99),
                           np.log10(data.ed_inj.max()*1.01),
                           num=num)
    elif bintype == 'lin':
        bins = np.linspace(data.ed_inj.min(), data.ed_inj.max(), num=num)
    else:
        LOG.error('Bintype not recongnised. Use log or lin.')
    group = data.groupby(pd.cut(data.ed_inj,bins))
    rec_prob = (pd.DataFrame({'min_ed_inj' : bins[:-1],
                             'max_ed_inj' : bins[1:],
                             'mid_ed_inj' : (bins[:-1]+bins[1:])/2.,
                             'rec_prob' : group.rec.mean()})
                             .reset_index()
                             .drop('ed_inj',axis=1))

    return rec_prob

def equivalent_duration_ratio(data, bins=30, bintype='log', fixed_bins=False):
    """
    Calculate a look-up table that returns the ratio of a flare's recovered
    equivalent duration to the injected one.

    Parameters
    -----------
    data : DataFrame
        Table with columns that contain injected and recovered equivalent
        durations of synthetic flares.
    bins : 30 or int
        Maximum size of look-up table.
    bintype : 'log' or 'lin'

    fixed_bins : False or bool

    Return
    ------
    DataFrame that gives bin edges in equivalent duration and the ratio of
    equivalent durations in these bins.
    """
    d = data[data.ed_rec>0]
    d = d[['ed_inj','ed_rec']]
    d['rel'] = (d.ed_rec/d.ed_inj).astype(float)
    if fixed_bins == False:
        num = min(int(np.rint(data.shape[0]/100)), bins + 1)
    else:
        num = bins + 1

    if bintype=='log':
        bins = np.logspace(np.log10(d.ed_rec.min() * .99),
                           np.log10(d.ed_rec.max() * 1.01),
                           num=num)
    elif bintype == 'lin':
        bins = np.linspace(d.ed_rec.min(), d.ed_rec.max(), num=num)
    group = d.groupby(pd.cut(d.ed_rec,bins))
    ed_rat = (pd.DataFrame({'min_ed_rec' : bins[:-1],
                             'max_ed_rec' : bins[1:],
                             'mid_ed_rec' : (bins[:-1]+bins[1:])/2.,
                             'rel_rec' : 1/group.rel.mean()})
                             .reset_index()
                             .drop('ed_rec',axis=1)
                             .dropna(how='any'))

    return ed_rat

def characterize_one_flare(flc, f, ampl_factor=[0.01,2.], dur_factor=[0.01,2.],
                           iterations=200, complexity='simple_only',
                           ratio_factor=[0.5,2.], **kwargs):
    """
    Takes the data of a recovered flare and return the data with
    information about recovery probability and corrected equivalent
    duration.

    Parameters
    -----------
    flc : FlareLightCurve

    f : Series
        A row from the FlareLightCurve.flares DataFrame
    dur_factor
    ampl_factor
    ratio_factor : 0.2 or float

    iterations : 200 or int
        Number of iterations for injection/recovery sampling.
    complexity : 'simple_only' or str
        If 'simple_only' is used, all superimposed flares will be ignored.
        If 'complex_only' is used, all simple flares will be ignored.
        If 'all' is used, all flares are used for characterization but the
        fraction of complex flares is returned.
    kwargs : dict
        Keyword arguments to pass to sample_flare_recovery.

    Return
    -------
    Same as f but with 'ed_rec_corr' and 'rec_prob' keys added.
    """
    for a in [ratio_factor, ampl_factor, dur_factor]:
        if a[1] < 1.:
            LOG.exception('All maximum factors must be >=1.')
        elif a[0] >1.:
            LOG.exception('All minimum factors must be <=1.')
    def relr(x, ed_rat):
        try:
            note=''
            erc = ed_rat.rel_rec[(x>ed_rat.min_ed_rec) & (x<=ed_rat.max_ed_rec)].iloc[0]
            return erc, note
        except IndexError:
            LOG.info('Recovery probability may be too low to find enough injected'
                     ' flares to calculate a corrected ED. Will return recovery '
                     'probability for recovered ED instead of corrected ED.')
            note = '(for uncorrected ED)'
            return 0, note

    def recr(x, rec_prob):
        return rec_prob.rec_prob[(x>rec_prob.min_ed_inj) & (x<=rec_prob.max_ed_inj)].iloc[0]

    f2 = copy.copy(f)

    if f.ampl_rec < 0:
        LOG.info('Amplitude is smaller than global iterative median (not '
                  'necessarily the local). Recovery very unlikely.\n')
        f2['ed_rec_corr'] = 0.
        f2['rec_prob'] = 0.
        return f2, [],[]

    dur = (f.tstop - f.tstart) * np.array(dur_factor)
    rat = f.ampl_rec / (f.tstop - f.tstart) * np.array(ratio_factor)
    ampl = f.ampl_rec * np.array(ampl_factor)

    # If the scale factor cuts out too much from the ampl-dur parameter space,
    # shrink it accordingly:
    from operator import le,ge
    for (i, op) in [(0,ge),(1,le)]:
        if op(dur[i],ampl[i]/rat[i]):
            ampl[i] = rat[i]*dur[i]

    data, g = flc.sample_flare_recovery(ampl=ampl, dur=dur, rat=rat,
                                        iterations = iterations, mode='uniform_ratio',
                                        **kwargs)

    data = resolve_complexity(data, complexity=complexity)
    if data[data.ed_rec>0].shape[0]==0:
        LOG.info('This is just an outlier. Synthetic injection yields no recoveries.\n')
        f2['ed_rec_corr'] = 0.
        f2['rec_prob'] = 0.
        return f2, data, g
    else:
        data = data[(data.ed_inj > 0.05*f.ed_rec) & (data.ed_inj < 20.*f.ed_rec)]
        rec_prob = recovery_probability(data, bintype='lin')
        ed_rat = equivalent_duration_ratio(data, bintype='lin')
        erc, note = relr(f2.ed_rec, ed_rat)
        if erc == 0:
            rp = recr(f2.ed_rec, rec_prob)
        else:
            erc *= f2.ed_rec
            rp = recr(erc, rec_prob)
        LOG.info('Corrected ED = {}. Recovery probability {} = {}.\n'.format(erc, note, rp))
        f2['ed_rec_corr'] = erc
        f2['rec_prob'] = rp

    return f2, data, g

def resolve_complexity(data, complexity='all'):
    """
    Either deal with only simple or complex flares or ignore the difference and
    just give the fraction of complex flares in the synthetic sample.
    """
    if complexity == 'simple_only':
        data = data[data.complex == 1]
        data.loc[:,'complex_fraction'] = 0.
        return data
    elif complexity == 'complex_only':
        data = data[data.complex > 1]
        data.loc[:,'complex_fraction'] = 0.
        return data
    elif complexity == 'all':
        count_complex = data.complex.astype(float).sum()
        size = data.shape[0]
        data['complex_fraction'] = (count_complex-size)/size
        return data
