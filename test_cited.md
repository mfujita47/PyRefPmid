<!-- filepath: c:\Users\sunda\Documents\OneDrive - 近畿大学\Scripts\Python\PyRef\test.md -->
# PyRefPmid テスト用ファイル

このファイルは `PyRefPmid.py` スクリプトの動作をテストするために使用されます。
様々なパターンのPMID引用を含んでいます。

**テストの目的:**

*   単独のPMID引用が正しく認識され、番号付けされること。
*   連続するPMID引用（スペース区切り、スペースなし、改行区切り）がグループとして認識され、各PMIDがソートされた上で番号付けされること。
*   本文中でのPMIDの出現順と、連続引用グループ内でのソート順に基づいて、文献リストの番号が一意に決定されること。
*   存在しないPMID（例: `99999999`）が引用された場合でも、番号は付与され、文献リストにはエラーとして表示されること。
*   同じPMIDが複数回引用された場合、同じ参照番号が使用されること。
*   `[pm ...]()` と `[pmid ...]()` の両方の形式が認識されること（大文字・小文字区別なし）。
*   括弧 `()` 内のテキストは無視されること。
*   処理後に `References` セクションが正しく生成・追記されること。
*   `References` セクションのヘッダーレベルが適切であること。

**期待される出力の確認ポイント:**

1.  **本文中の引用置換**: 全ての `[pm...]` および `[pmid...]` 形式の引用が、`(番号)` や `(番号1,番号2)` のような形式に置換されているか。
2.  **`References` セクションの生成**: ファイルの末尾に `## References` (または適切なレベルのヘッダー) が生成されているか。
3.  **文献リストの順序と内容**:
    *   文献リストの番号は、本文中の最初の出現順（連続引用の場合はグループとしての最初の出現、グループ内ではPMIDの昇順）に従っているか。
    *   各文献情報（著者、タイトル、雑誌、年など）が正しく取得・表示されているか。
    *   存在しないPMIDについては、エラーメッセージ（例: `論文情報の取得に失敗しました`）が表示されているか。
    *   PMIDへのリンクが正しく生成されているか。

---

以下、テスト用の引用を含みます。

## 基本的な引用

最初の引用は (1) です。これは重要な論文です。

次に、別の引用 (2) を追加します。

同じ引用 (1) を再度使用します。

存在しない PMID (3) も試してみましょう。

最後に、もう一つ有効な引用 (4) を入れます。

## 連続する引用のテスト

### 2つの連続 (スペースなし、ソート前)

(5,6)

### 2つの連続 (スペースあり、ソート前)

(7,8)

### 3つの連続 (ソート済み)

(9-11)

### 4つの連続 (未ソート)

(12-15)

### 連続するPMID (重複あり、未ソート)

(16,17)

### 改行を含む連続PMID (ソート前)

これは改行を含むテストです。
(18,19)
このように書かれます。

## 混在パターンのテスト

単独引用 (20) と、連続引用 (21,22) があり、その後にまた単独 (23) が続きます。

文末の連続PMIDのテストです (24,25).

PMIDの間にハイフンがある場合: (26,27) と (28)-(29).

複雑な組み合わせ: (30,31) and (32), then (33-35).

### 新規引用と再引用の混在連続パターン

これは、新規のPMIDと、本文中で既に出現したPMIDが混在して連続しているパターンです。
例えば、(1,36-39) のような場合です。
ここで `10000001` は既出のPMIDです。

もう一つの例: (2,9,40,41) のように、複数の既出PMIDが新規PMIDと混ざる場合。

## 別のセクション

ここにも引用 (2) を含めます。

そして、新しい連続引用 (42-45) をテストします。

## References

1. Artoni M, Birman JL. Quantum-optical properties of polariton waves. Phys Rev B Condens Matter 1991;44:3736-3756. doi: 10.1103/physrevb.44.3736. [10000001](https://pubmed.ncbi.nlm.nih.gov/10000001/)
2. Amiotti M, Borghesi A, Marabelli F, Guizzetti G, Nava F. Optical study of niobium disilicide polycrystalline films. Phys Rev B Condens Matter 1991;44:3757-3761. doi: 10.1103/physrevb.44.3757. [10000002](https://pubmed.ncbi.nlm.nih.gov/10000002/)
3. [PMID 99999999] - 論文情報の取得に失敗しました (cannot get document summary)。
4. Betbeder-Matibet O, Combescot M, Tanguy C. Optical Stark effect of the exciton. III. Absorption strength. Phys Rev B Condens Matter 1991;44:3762-3771. doi: 10.1103/physrevb.44.3762. [10000003](https://pubmed.ncbi.nlm.nih.gov/10000003/)
5. Brey L. Energy spectrum of electrons in a parabolic quantum well in a strong magnetic field. Phys Rev B Condens Matter 1991;44:3772-3781. doi: 10.1103/physrevb.44.3772. [10000004](https://pubmed.ncbi.nlm.nih.gov/10000004/)
6. Bryant GW. Understanding quantum-box resonant-tunneling spectroscopy: Fine structure at Fermi-level crossings. Phys Rev B Condens Matter 1991;44:3782-3786. doi: 10.1103/physrevb.44.3782. [10000005](https://pubmed.ncbi.nlm.nih.gov/10000005/)
7. Cai YQ, Riley JD, Leckey RC, Usher B, Fraxedas J, Ley L. Photoemission study of the electronic structure of a (GaAs)2/(AlAs)2 superlattice. Phys Rev B Condens Matter 1991;44:3787-3792. doi: 10.1103/physrevb.44.3787. [10000006](https://pubmed.ncbi.nlm.nih.gov/10000006/)
8. Coleridge PT. Small-angle scattering in two-dimensional electron gases. Phys Rev B Condens Matter 1991;44:3793-3801. doi: 10.1103/physrevb.44.3793. [10000007](https://pubmed.ncbi.nlm.nih.gov/10000007/)
9. Elswijk HB, Dijkkamp D, van Loenen EJ. Geometric and electronic structure of Sb on Si(111) by scanning tunneling microscopy. Phys Rev B Condens Matter 1991;44:3802-3809. doi: 10.1103/physrevb.44.3802. [10000008](https://pubmed.ncbi.nlm.nih.gov/10000008/)
10. Glazman LI, Jonson M. Breakdown of conductance quantization and mesoscopic fluctuations in the quasiballistic regime. Phys Rev B Condens Matter 1991;44:3810-3820. doi: 10.1103/physrevb.44.3810. [10000009](https://pubmed.ncbi.nlm.nih.gov/10000009/)
11. Hawrylak P. Optical properties of a two-dimensional electron gas: Evolution of spectra from excitons to Fermi-edge singularities. Phys Rev B Condens Matter 1991;44:3821-3828. doi: 10.1103/physrevb.44.3821. [10000010](https://pubmed.ncbi.nlm.nih.gov/10000010/)
12. Heldmann K, Teich WG, Mahler G. Charge-transfer excitations on a linear chain. Phys Rev B Condens Matter 1991;44:3829-3834. doi: 10.1103/physrevb.44.3829. [10000011](https://pubmed.ncbi.nlm.nih.gov/10000011/)
13. Maschke K, Schreiber M. Unified description of coherent and dissipative electron transport. Phys Rev B Condens Matter 1991;44:3835-3841. doi: 10.1103/physrevb.44.3835. [10000012](https://pubmed.ncbi.nlm.nih.gov/10000012/)
14. Matsuura M, Tonnerre JM, Cargill GS 3rd. Lattice parameters and local atomic structure of silicon-rich Si-Ge/Si (100) films. Phys Rev B Condens Matter 1991;44:3842-3849. doi: 10.1103/physrevb.44.3842. [10000013](https://pubmed.ncbi.nlm.nih.gov/10000013/)
15. Register LF, Stroscio MA, Littlejohn MA. Constraints on the polar-optical-phonon influence functional in heterostructures. Phys Rev B Condens Matter 1991;44:3850-3853. doi: 10.1103/physrevb.44.3850. [10000014](https://pubmed.ncbi.nlm.nih.gov/10000014/)
16. Slaughter JM, Shapiro A, Kearney PA, Falco CM. Growth of molybdenum on silicon: Structure and interface formation. Phys Rev B Condens Matter 1991;44:3854-3863. doi: 10.1103/physrevb.44.3854. [10000015](https://pubmed.ncbi.nlm.nih.gov/10000015/)
17. Vassell MO, Lee J. Wave-packet analysis of the quantum-confined Stark effect in coupled double quantum wells. Phys Rev B Condens Matter 1991;44:3864-3874. doi: 10.1103/physrevb.44.3864. [10000016](https://pubmed.ncbi.nlm.nih.gov/10000016/)
18. Washburn S, Haug RJ, Lee KY, Hong JM. Noise from backscattered electrons in the integer and fractional quantized Hall effects. Phys Rev B Condens Matter 1991;44:3875-3879. doi: 10.1103/physrevb.44.3875. [10000017](https://pubmed.ncbi.nlm.nih.gov/10000017/)
19. Trzeciakowski W, Gurioli M. Electric-field effects in semiconductor quantum wells. Phys Rev B Condens Matter 1991;44:3880-3890. doi: 10.1103/physrevb.44.3880. [10000018](https://pubmed.ncbi.nlm.nih.gov/10000018/)
20. Pederson MR, Jackson KA, Pickett WE. Local-density-approximation-based simulations of hydrocarbon interactions with applications to diamond chemical vapor deposition. Phys Rev B Condens Matter 1991;44:3891-3899. doi: 10.1103/physrevb.44.3891. [10000019](https://pubmed.ncbi.nlm.nih.gov/10000019/)
21. Ackland GJ. Interpretation of cluster structures in terms of covalent bonding. Phys Rev B Condens Matter 1991;44:3900-3908. doi: 10.1103/physrevb.44.3900. [10000020](https://pubmed.ncbi.nlm.nih.gov/10000020/)
22. Farazdel A, Dupuis M. All-electron ab initio self-consistent-field study of electron transfer in scanning tunneling microscopy at large and small tip-sample separations: Supermolecule approach. Phys Rev B Condens Matter 1991;44:3909-3915. doi: 10.1103/physrevb.44.3909. [10000021](https://pubmed.ncbi.nlm.nih.gov/10000021/)
23. Feibelman PJ. Pulay-type formula for surface stress in a local-density-functional, linear combination of atomic orbitals, electronic-structure calculation. Phys Rev B Condens Matter 1991;44:3916-3925. doi: 10.1103/physrevb.44.3916. [10000022](https://pubmed.ncbi.nlm.nih.gov/10000022/)
24. Fuchs G, Melinon P, Santos Aires F, Treilleux M, Cabaud B, Hoareau A. Cluster-beam deposition of thin metallic antimony films: Cluster-size and deposition-rate effects. Phys Rev B Condens Matter 1991;44:3926-3933. doi: 10.1103/physrevb.44.3926. [10000023](https://pubmed.ncbi.nlm.nih.gov/10000023/)
25. Gumbsch P, Daw MS. Interface stresses and their effects on the elastic moduli of metallic multilayers. Phys Rev B Condens Matter 1991;44:3934-3938. doi: 10.1103/physrevb.44.3934. [10000024](https://pubmed.ncbi.nlm.nih.gov/10000024/)
26. Hitchen GJ, Thurgate SM, Jennings PJ. Determination of the surface-potential barrier of Cu(001) from low-energy-electron-diffraction fine structure. Phys Rev B Condens Matter 1991;44:3939-3942. doi: 10.1103/physrevb.44.3939. [10000025](https://pubmed.ncbi.nlm.nih.gov/10000025/)
27. Janz S, Pedersen K, van Driel HM. Dispersion and anisotropy of the optical second-harmonic response of single-crystal Al surfaces. Phys Rev B Condens Matter 1991;44:3943-3954. doi: 10.1103/physrevb.44.3943. [10000026](https://pubmed.ncbi.nlm.nih.gov/10000026/)
28. Jiménez Sandoval S, Yang D, Frindt RF, Irwin JC. Raman study and lattice dynamics of single molecular layers of MoS2. Phys Rev B Condens Matter 1991;44:3955-3962. doi: 10.1103/physrevb.44.3955. [10000027](https://pubmed.ncbi.nlm.nih.gov/10000027/)
29. Mizes H, Conwell E. Conduction in ladder polymers. Phys Rev B Condens Matter 1991;44:3963-3969. doi: 10.1103/physrevb.44.3963. [10000028](https://pubmed.ncbi.nlm.nih.gov/10000028/)
30. Russier V V, Mijoule C. Theoretical study of alkali-metal-atom adsorption on transition-metal surfaces by a cluster approach: Finite-size effects. Phys Rev B Condens Matter 1991;44:3970-3980. doi: 10.1103/physrevb.44.3970. [10000029](https://pubmed.ncbi.nlm.nih.gov/10000029/)
31. Steffen HJ, Roux CD, Marton D, Rabalais JW. Auger-electron-spectroscopy analysis of chemical states in ion-beam-deposited carbon layers on graphite. Phys Rev B Condens Matter 1991;44:3981-3990. doi: 10.1103/physrevb.44.3981. [10000030](https://pubmed.ncbi.nlm.nih.gov/10000030/)
32. Vandenberg JM, Macrander AT, Hamm RA, Panish MB. Evidence for intrinsic interfacial strain in lattice-matched InxGa1-xAs/InP heterostructures. Phys Rev B Condens Matter 1991;44:3991-3994. doi: 10.1103/physrevb.44.3991. [10000031](https://pubmed.ncbi.nlm.nih.gov/10000031/)
33. Valent R, Hirschfeld PJ, Anglés d'Auriac JC. Rigorous lower bounds on the ground-state energy of correlated Fermi systems. Phys Rev B Condens Matter 1991;44:3995-3998. doi: 10.1103/physrevb.44.3995. [10000032](https://pubmed.ncbi.nlm.nih.gov/10000032/)
34. Schwab H, Lyssenko VG, Hvam JM. Spontaneous photon echo from bound excitons in CdSe. Phys Rev B Condens Matter 1991;44:3999-4001. doi: 10.1103/physrevb.44.3999. [10000033](https://pubmed.ncbi.nlm.nih.gov/10000033/)
35. Bauer A, Prietsch M, Molodtsov S, Laubschat C, Kaindl G. Systematic study of the surface photovoltaic effect in photoemission. Phys Rev B Condens Matter 1991;44:4002-4005. doi: 10.1103/physrevb.44.4002. [10000034](https://pubmed.ncbi.nlm.nih.gov/10000034/)
36. Peng JP, Zhou SX, Shen XC. Faraday rotation in quasi-two-dimensional electron systems in the quantized Hall regime. Phys Rev B Condens Matter 1991;44:4021-4023. doi: 10.1103/physrevb.44.4021. [10000039](https://pubmed.ncbi.nlm.nih.gov/10000039/)
37. de Beauvais C, Rouxel D, Bigeard B, Mutaftschiev B. Thermal-energy atom-scattering study of Pb submonolayers on Cu(110). Phys Rev B Condens Matter 1991;44:4024-4027. doi: 10.1103/physrevb.44.4024. [10000040](https://pubmed.ncbi.nlm.nih.gov/10000040/)
38. Saint Jean M, Frétigny C. Gyromagnetic factor in first and second stages of graphite intercalation compounds. Phys Rev B Condens Matter 1991;44:4028-4031. doi: 10.1103/physrevb.44.4028. [10000041](https://pubmed.ncbi.nlm.nih.gov/10000041/)
39. Rapcewicz K, Ashcroft NW. Fluctuation attraction in condensed matter: A nonlocal functional approach. Phys Rev B Condens Matter 1991;44:4032-4035. doi: 10.1103/physrevb.44.4032. [10000042](https://pubmed.ncbi.nlm.nih.gov/10000042/)
40. Eteläniemi V V, Michel EG, Materlik G. X-ray standing-wave study of Cs/Si(111)7 x 7. Phys Rev B Condens Matter 1991;44:4036-4039. doi: 10.1103/physrevb.44.4036. [10000043](https://pubmed.ncbi.nlm.nih.gov/10000043/)
41. Meng Y, Anderson JR, Hermanson JC, Lapeyre GJ. Hole plasmon excitations on a p-type GaAs(110) surface. Phys Rev B Condens Matter 1991;44:4040-4043. doi: 10.1103/physrevb.44.4040. [10000044](https://pubmed.ncbi.nlm.nih.gov/10000044/)
42. Goldberg BB, Heiman D, Dahl M, Pinczuk A, Pfeiffer L, West K. Localization and many-body interactions in the quantum Hall effect determined by polarized optical emission. Phys Rev B Condens Matter 1991;44:4006-4009. doi: 10.1103/physrevb.44.4006. [10000035](https://pubmed.ncbi.nlm.nih.gov/10000035/)
43. Rune GC, Holtz PO, Sundaram M, Merz JL, Gossard AC, Monemar B. Dependence of the binding energy of the acceptor on its position in a GaAs/AlxGa1-xAs quantum well. Phys Rev B Condens Matter 1991;44:4010-4013. doi: 10.1103/physrevb.44.4010. [10000036](https://pubmed.ncbi.nlm.nih.gov/10000036/)
44. Feng S, Spivak BZ. Voltage fluctuations in mesoscopic conductors with single-channel leads: Electronic speckle patterns. Phys Rev B Condens Matter 1991;44:4014-4016. doi: 10.1103/physrevb.44.4014. [10000037](https://pubmed.ncbi.nlm.nih.gov/10000037/)
45. Dunstan DJ, Prins AD, Gil B, Faurie JP. Phase transitions in CdTe/ZnTe strained-layer superlattices. Phys Rev B Condens Matter 1991;44:4017-4020. doi: 10.1103/physrevb.44.4017. [10000038](https://pubmed.ncbi.nlm.nih.gov/10000038/)