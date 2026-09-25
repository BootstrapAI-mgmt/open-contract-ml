# References

The consolidated bibliography for this repository. Every `[Key]` citation in
the shipped documents resolves here.

## How citations work here

**Short-key scheme.** `[FirstAuthorYear]` — for example `[Bathe2014]`. Where two
works share a first author and year, a lowercase suffix disambiguates
(`[Smith2020a]`, `[Smith2020b]`). This is the scheme the documents already used
in prose; this file is where it terminates.

**Cite by reference, never by quotation.** A citation here is author, title,
publication, year, and a DOI or stable URL. It is not a passage lifted from the
source. Third-party text — verbatim excerpts, licensed datasets, vendored
snippets — is never reproduced in this repository, whatever its licence would
appear to allow. Where a shipped document needs to convey what a source found,
it restates the finding in its own words and cites the source. That rule is
enforced by `tests/test_provenance.py::test_no_verbatim_third_party_text`.

**No pointer may dangle.** A citation must resolve to something a reader of this
repository can actually reach: an entry below, or a file this repository ships.
Earlier revisions of these documents cited sources by anchors that resolved to
nothing a reader could open; those anchors have been replaced by the entries
below.
`tests/test_link_integrity.py` is the standing gate against a recurrence.

## Bibliography

| Key | Reference | Cited for |
|---|---|---|
| Bathe2014 | Bathe, K.-J. (2014). *Finite Element Procedures*, 2nd edition. Self-published; 4th printing. ISBN 978-0-9790049-0-2. (1st ed.: Prentice-Hall, 1996.) | Galerkin finite-element machinery shared across the structural and thermal cells |
| Battaglia2018 | Battaglia, P. W., Hamrick, J. B., Bapst, V., Sanchez-Gonzalez, A., Zambaldi, V., et al. (2018). Relational inductive biases, deep learning, and graph networks. arXiv:1806.01261. https://doi.org/10.48550/arXiv.1806.01261 | graph-network encoder/decoder framing for unstructured-mesh inputs |
| Bazilevs2013 | Bazilevs, Y., Takizawa, K., & Tezduyar, T. E. (2013). *Computational Fluid–Structure Interaction: Methods and Applications*. Wiley. ISBN 978-0-470-97877-1. https://doi.org/10.1002/9781118483565 | coupling-scheme taxonomy for the thermo-mechanical chain link |
| Belytschko2014 | Belytschko, T., Liu, W. K., Moran, B., & Elkhodary, K. I. (2014). *Nonlinear Finite Elements for Continua and Structures*, 2nd edition. Wiley. ISBN 978-1-118-63270-3. | nonlinear structural-mechanics FE foundations |
| Bergman2017 | Bergman, T. L., Lavine, A. S., Incropera, F. P., & DeWitt, D. P. (2017). *Fundamentals of Heat and Mass Transfer*, 8th edition. Wiley. ISBN 978-1-118-98917-3. | conduction-equation derivations; Biot / Fourier dimensionless framework |
| Chen2016 | Chen, T., & Guestrin, C. (2016). XGBoost: A Scalable Tree Boosting System. *KDD 2016*, 785–794. arXiv:1603.02754. https://doi.org/10.1145/2939672.2939785 | gradient-boosted-tree surrogate family for tabular targets |
| Chen2018 | Chen, R. T. Q., Rubanova, Y., Bettencourt, J., & Duvenaud, D. K. (2018). Neural Ordinary Differential Equations. *NeurIPS 2018*. arXiv:1806.07366. https://doi.org/10.48550/arXiv.1806.07366 | Neural-ODE latent dynamics; adjoint backpropagation |
| Goodfellow2016 | Goodfellow, I., Bengio, Y., & Courville, A. (2016). *Deep Learning*. MIT Press. ISBN 978-0-262-03561-3. https://www.deeplearningbook.org/ | feedforward-network (MLP) definitions |
| Grinsztajn2022 | Grinsztajn, L., Oyallon, E., & Varoquaux, G. (2022). Why do tree-based models still outperform deep learning on tabular data? *NeurIPS 2022*, Datasets and Benchmarks Track. arXiv:2207.08815. https://doi.org/10.48550/arXiv.2207.08815 | tree models carry no smoothness prior — the falsifier's smoothness-of-sweeps cell |
| Hastie2009 | Hastie, T., Tibshirani, R., & Friedman, J. (2009). *The Elements of Statistical Learning: Data Mining, Inference, and Prediction*, 2nd edition. Springer. ISBN 978-0-387-84857-0. https://doi.org/10.1007/978-0-387-84858-7 | trees partition the feature space into rectangles and fit constants on them, and the loss of smoothness that follows |
| HsuBazilevs2012 | Hsu, M.-C., & Bazilevs, Y. (2012). Fluid–structure interaction modeling of wind turbines: simulating the full machine. *Computational Mechanics*, 50(6), 821–833. https://doi.org/10.1007/s00466-012-0772-0 | worked fluid–structure coupling precedent |
| Hughes2000 | Hughes, T. J. R. (2000). *The Finite Element Method: Linear Static and Dynamic Finite Element Analysis*. Dover. ISBN 0-486-41181-8. (Reprint of Prentice-Hall, 1987.) | linear static and dynamic FE monograph |
| Jackson1998 | Jackson, J. D. (1998). *Classical Electrodynamics*, 3rd edition. Wiley. ISBN 978-0-471-30932-1. | Maxwell-equation derivations; magneto-quasi-static reduction |
| Jin2001 | Jin, R., Chen, W., & Simpson, T. W. (2001). Comparative studies of metamodelling techniques under multiple modelling criteria. *Structural and Multidisciplinary Optimization*, 23(1), 1–13. https://doi.org/10.1007/s00158-001-0160-4 | accuracy parity between metamodel families at large sample size; polynomial robustness under observation noise |
| Karniadakis2021 | Karniadakis, G. E., Kevrekidis, I. G., Lu, L., Perdikaris, P., Wang, S., & Yang, L. (2021). Physics-informed machine learning. *Nature Reviews Physics*, 3(6), 422–440. https://doi.org/10.1038/s42254-021-00314-5 | physics-informed framing for the residual-loss ablation |
| Kaw2012 | Kaw, A. (2012). Bisection method of solving a nonlinear equation (Textbook Ch. 03.03). *Holistic Numerical Methods*, University of South Florida (open courseware). https://nm.mathforcollege.com/mws/gen/03nle/mws_gen_nle_txt_bisection.pdf | the continuity-and-sign-change precondition the inverse-problem cell relies on |
| Ke2017 | Ke, G., Meng, Q., Finley, T., Wang, T., Chen, W., Ma, W., Ye, Q., & Liu, T.-Y. (2017). LightGBM: A Highly Efficient Gradient Boosting Decision Tree. *NeurIPS 30*. https://proceedings.neurips.cc/paper/2017/hash/6449f44a102fde848669bdd9eb6b76fa-Abstract.html | gradient-boosted-tree surrogate family for tabular targets |
| Kennedy2013 | Kennedy, P. K., & Zheng, R. (2013). *Flow Analysis of Injection Molds*, 2nd edition. Hanser. ISBN 978-1-56990-512-8. https://doi.org/10.3139/9781569905227 | injection-moulding flow analysis underlying the warpage cell |
| KimeldorfWahba1970 | Kimeldorf, G. S., & Wahba, G. (1970). A correspondence between Bayesian estimation on stochastic processes and smoothing by splines. *The Annals of Mathematical Statistics*, 41(2), 495–502. https://doi.org/10.1214/aoms/1177697089 | reversion of the posterior mean to the prior mean away from the data — the extrapolation cell |
| Kovachki2023 | Kovachki, N., Li, Z., Liu, B., Azizzadenesheli, K., Bhattacharya, K., Stuart, A., & Anandkumar, A. (2023). Neural operator: Learning maps between function spaces with applications to PDEs. *Journal of Machine Learning Research*, 24(89), 1–97. https://www.jmlr.org/papers/v24/21-1524.html | operator-learning framing; neural-operator family definition |
| Lee2020 | Lee, K., & Carlberg, K. T. (2020). Model reduction of dynamical systems on nonlinear manifolds using deep convolutional autoencoders. *Journal of Computational Physics*, 404, 108973. arXiv:1812.08373. https://doi.org/10.1016/j.jcp.2019.108973 | nonlinear-manifold reduced-order modelling via autoencoder projection |
| Li2021 | Li, Z., Kovachki, N., Azizzadenesheli, K., Liu, B., Bhattacharya, K., Stuart, A., & Anandkumar, A. (2021). Fourier Neural Operator for Parametric Partial Differential Equations. *ICLR 2021*. arXiv:2010.08895. https://doi.org/10.48550/arXiv.2010.08895 | FNO topology (lifting, Fourier blocks, projection) and its defaults |
| McElfresh2023 | McElfresh, D., Khandagale, S., Valverde, J., Prasad C, V., Ramakrishnan, G., Goldblum, M., & White, C. (2023). When do neural nets outperform boosted trees on tabular data? *NeurIPS 2023*, Datasets and Benchmarks Track. arXiv:2305.02997. https://doi.org/10.48550/arXiv.2305.02997 | benchmark evidence that family choice is often not the dominant lever |
| Miner1945 | Miner, M. A. (1945). Cumulative Damage in Fatigue. *Journal of Applied Mechanics*, 12(3), A159–A164. https://doi.org/10.1115/1.4009458 | linear cumulative-damage rule; log-life target and scatter range |
| Misic2020 | Mišić, V. V. (2020). Optimization of tree ensembles. *Operations Research*, 68(5), 1605–1624. arXiv:1705.10883. https://doi.org/10.1287/opre.2019.1928 | exact inversion of a tree ensemble is NP-hard — the complexity bound on the inverse-problem cell |
| Paris1963 | Paris, P., & Erdogan, F. (1963). A Critical Analysis of Crack Propagation Laws. *Journal of Basic Engineering*, 85(4), 528–533. https://doi.org/10.1115/1.3656900 | linear-elastic crack-growth boundary of the fatigue cell |
| Patankar1980 | Patankar, S. V. (1980). *Numerical Heat Transfer and Fluid Flow*. Hemisphere Publishing. ISBN 0-89116-522-3. https://doi.org/10.1201/9781482234213 | finite-volume discretisation family |
| Rasmussen2006 | Rasmussen, C. E., & Williams, C. K. I. (2006). *Gaussian Processes for Machine Learning*. MIT Press. ISBN 0-262-18253-X. http://www.gaussianprocess.org/gpml/ | Gaussian-process definition and the UQ companion model |
| Roark2020 | Young, W. C., Budynas, R. G., & Sadegh, A. M. (2020). *Roark's Formulas for Stress and Strain*, 9th edition. McGraw-Hill. ISBN 978-0-07-176235-9. | handbook-tier analytical stress formulas; low-fidelity benchmark |
| Ronneberger2015 | Ronneberger, O., Fischer, P., & Brox, T. (2015). U-Net: Convolutional Networks for Biomedical Image Segmentation. *MICCAI 2015*. arXiv:1505.04597. https://doi.org/10.48550/arXiv.1505.04597 | U-Net encoder–decoder topology; CNN inductive bias on grid inputs |
| Slotnick2014 | Slotnick, J. P., Khodadoust, A., Alonso, J., Darmofal, D., Gropp, W., Lurie, E., & Mavriplis, D. J. (2014). *CFD Vision 2030 Study: A Path to Revolutionary Computational Aerosciences*. NASA/CR–2014-218178. NASA Langley Research Center. https://ntrs.nasa.gov/citations/20140003093 | state-of-practice and open-problem framing for external-aero CFD |
| Stephens2001 | Stephens, R. I., Fatemi, A., Stephens, R. R., & Fuchs, H. O. (2001). *Metal Fatigue in Engineering*, 2nd edition. Wiley. ISBN 978-0-471-51059-1. | Marin factors; mean-stress correction families; multiaxial criteria |
| Suresh1998 | Suresh, S. (1998). *Fatigue of Materials*, 2nd edition. Cambridge University Press. ISBN 978-0-521-57847-9. | fatigue-mechanism framing |
| Trefethen2013 | Trefethen, L. N. (2013). *Approximation Theory and Approximation Practice*. SIAM. ISBN 978-1-611972-39-9. http://www.chebfun.org/ATAP/ | equispaced polynomial interpolation is exponentially ill-conditioned — the high-degree pathology |
| WangShan2007 | Wang, G. G., & Shan, S. (2007). Review of metamodeling techniques in support of engineering design optimization. *Journal of Mechanical Design*, 129(4), 370–380. https://doi.org/10.1115/1.2429697 | no metamodel family is uniformly superior; kriging and RBF are more noise-sensitive than polynomials |
| Xu2021 | Xu, K., Zhang, M., Li, J., Du, S. S., Kawarabayashi, K., & Jegelka, S. (2021). How neural networks extrapolate: from feedforward to graph neural networks. *ICLR 2021*. arXiv:2009.11848. https://doi.org/10.48550/arXiv.2009.11848 | ReLU MLPs extrapolate linearly along rays from the origin — the far-field behaviour cell |
| Yuksel2026 | Yüksel, N. (2026). Comparative analysis of surrogate models for nonlinear behavior prediction of an aircraft landing gear bracket. *Journal of Engineering Research*, in press (corrected proof, 7 January 2026). https://doi.org/10.1016/j.jer.2026.01.005 | peer-reviewed peak-stress gradient-boosting precedent |
| Zienkiewicz2013 | Zienkiewicz, O. C., Taylor, R. L., & Zhu, J. Z. (2013). *The Finite Element Method: Its Basis and Fundamentals*, 7th edition. Butterworth-Heinemann. ISBN 978-1-85617-633-0. https://doi.org/10.1016/C2009-0-24909-9 | variational methods and error estimation |

## Adding a reference

Add the key here first, then cite it as `[Key]` in the document. Record author,
title, publication, year, and a DOI or stable URL. Do not paste text from the
source; state the point in the document's own words and cite it.
