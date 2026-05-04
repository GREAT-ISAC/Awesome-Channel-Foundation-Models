# Awesome CFMs (Channel Foundation Models)

A curated list of Channel Foundation Models (CFMs) that demonstrates how **AI empowers next-generation wireless communication**. As we advance towards 6G, CFMs are emerging as a critical technology to replace traditional task-specific modules with generalized, pretrained representations. This repository aims to collect CFMs, serving as a vital resource for facilitating research and development in **AI-native wireless networks**. These models leverage large-scale data to solve complex physical layer problems, offering new possibilities for channel-related tasks.

**This list will be continuously updated.** If there are any omissions in the collection of the papers, please feel free to contact Jun Jiang at jun_jiang@shu.edu.cn.

- Welcome to contact us to add your own work or other excellent CFMs to this list! We will review and update it in a timely manner.
- For any questions, suggestions or corrections, please open an issue or contact the maintainers.

Last Updated: May 4, 2026

## Contents

- [Surveys & Perspectives](#surveys--perspectives)
- [Generative Pretraining Approaches](#generative-pretraining-approaches)
  - [CSI-based](#csi-based)
  - [IQ-based](#iq-based)
  - [Others](#others)
- [Discriminative Pretraining Approaches](#discriminative-pretraining-approaches)
  - [CSI-based](#csi-based-1)
  - [IQ-based](#iq-based-1)
- [Other Pretraining Approaches](#other-pretraining-approaches)
- [Multitask Pretraining Approaches](#multitask-pretraining-approaches)
- [License](#license)

## Surveys & Perspectives

- **[Towards channel foundation models (CFMs): Motivations, methodologies and opportunities](https://arxiv.org/abs/2507.13637)**
  - **Paper Authors**: `Jun Jiang, Yuan Gao, Xinyi Wu, Shugong Xu`
  - **Summary**: This paper introduces the concept of channel foundation models (CFMs) for the first time, providing a comprehensive survey on motivations, methodologies, and future opportunities.

- **[6G Native AI and Channel Foundation Models](docs/6G%20Native%20AI%20and%20Channel%20Foundation%20Models.pdf)**
  - **Paper Authors**: `Shugong Xu, Jun Jiang`
  - **Abstract**: The integration of Artificial Intelligence (AI) and communication has emerged as a key target and hallmarks for sixth-generation wireless communication systems. Based on the discussion of the understanding of Native AI and the summary of the evolution of AI research paradigms in wireless communications, this paper points out that traditional task-specific AI models have various limitations, making them hardly serve as an important component of future 6G Native AI. Accordingly, we propose Channel Foundation Models (CFMs) and systematically introduce their pretraining methods, as well as their potential adaptation to various channel-related tasks. As an exploration and sharing on issues such as "what is Native AI" and "what kind of AI capabilities future 6G systems need", we argue that 6G Native AI must possess strong task adaptability and scenario generalization ability, and CFMs are expected to become one of the technical options for future 6G Native AI.
  - **摘要**: 人工智能（Artificial intelligence, AI）与通信的深度结合已成为6G的关键目标和标志之一。内生智能（Native AI）被认为是6G重要特征。本文在给出对内生智能理解探讨的基础上总结无线AI研究范式演进，指出基于监督学习的传统AI模型存在诸多局限，使其很难作为未来6G内生智能的重要组成部分。基于此，我们提出了信道基础模型（Channel Foundation Models, CFMs）并系统地介绍了其预训练方法，以及对各类信道相关任务的可能适配。作为对“什么是内生智能，什么样的AI能力是未来6G系统需要的”等问题的探讨和分享，我们认为6G内生智能需要具备强大任务适应性和场景泛化能力，CFMs有可能成为未来6G内生智能的技术选项之一。
  - **Note**: This invited position paper on CFM and 6G Native AI will be published by ZTE Communications soon (in Chinese). An early access version can be found in [CNKI](https://link.cnki.net/urlid/34.1228.TN.20260225.0923.002).

## Generative Pretraining Approaches

### CSI-based
- **[AirFM-DDA](https://arxiv.org/abs/2605.00020)**
  - **Paper Title**: `AirFM-DDA: Air-Interface Foundation Model in the Delay–Doppler–Angle Domain for AI-Native 6G`
  - **Paper Authors**: `Kejia Bian, Meixia Tao, Jianhua Mo, Zhiyong Chen, and Leyan Chen`
  - **Downstream Tasks**: Channel Extrapolation(time, freq), Channel Estimation

- **[WiMamba](https://arxiv.org/abs/2603.26367)**
  - **Paper Title**: `WiMamba: Linear-Scale Wireless Foundation Model`
  - **Paper Authors**: `Tomer Raviv, Nir Shlezinger`
  - **Downstream Tasks**: LOS/NLOS Identification, Channel Interpolation, Beam Prediction, Positioning

- **[MCM](https://ieeexplore.ieee.org/abstract/document/11442291)**
  - **Paper Title**: `Scalable Pre-Trained Masked Channel Model of Wireless Communications`
  - **Paper Authors**: `Jianhua Guo; Zhongsheng Deng; Zhen Qiao; Junkai Zhang; Jiang Xue; Dusit Niyato; Zongben Xu`
  - **Downstream Tasks**: Channel Extrapolation(time), Channel Estimation, Channel Feedback

- **[LWM-Temporal](https://arxiv.org/abs/2603.10024)**
  - **Paper Title**: `LWM-Temporal: Sparse Spatio-Temporal Attention for Wireless Channel Representation Learning`
  - **Paper Authors**: `Sadjad Alikhani, Akshay Malhotra, Shahab Hamidi-Rad, Ahmed Alkhateeb`
  - **Downstream Tasks**: Channel Extrapolation(time)

- **[HeterCSI](https://arxiv.org/abs/2601.18200)**
  - **Paper Title**: `HeterCSI: Channel-Adaptive Heterogeneous CSI Pretraining Framework for Generalized Wireless Foundation Models`
  - **Paper Authors**: `Chenyu Zhang, Xinchen Lyu, Chenshan Ren, Shuhan Liu, Qimei Cui, Xiaofeng Tao`
  - **Downstream Tasks**: Channel Extrapolation(time, freq)

- **[CSI-MAE](https://arxiv.org/abs/2601.03789)**
  - **Paper Title**: `CSI-MAE: A Masked Autoencoder-based Channel Foundation Model`
  - **Paper Authors**: `Jun Jiang, Xiaolong Ruan, Shugong Xu`
  - **Downstream Tasks**: Channel Extrapolation(time, freq), CSI Feedback, Positioning


- **[WiFo-2](https://arxiv.org/abs/2511.22222)**
  - **Paper Title**: `Foundation Model for Intelligent Wireless Communications`
  - **Paper Authors**: `Boxun Liu, Xuanyu Liu, Shijian Gao, Xiang Cheng, Liuqing Yang`
  - **Downstream Tasks**: LOS/NLOS Identification, Sub-6 to mmWave Beam Prediction, Positioning, Vision-aided Channel Extrapolation(freq), CSI Feedback, AoA Estimation, Cross-band Channel Prediction, Signal Detection

- **[UBERT](https://arxiv.org/abs/2509.11056)**
  - **Paper Title**: `BERT4beam: Large AI Model Enabled Generalized Beamforming Optimization`
  - **Paper Authors**: `Yuhang Li, Yang Lu, Wei Chen, Bo Ai, Zhiguo Ding, Dusit Niyato`
  - **Downstream Tasks**: Beamforming

- **[WiFo-CF](https://arxiv.org/abs/2508.04068)**
  - **Paper Title**: `WiFo-CF: Wireless Foundation Model for CSI Feedback`
  - **Paper Authors**: `Xuanyu Liu, Shijian Gao, Boxun Liu, Xiang Cheng, Liuqing Yang`
  - **Downstream Tasks**: CSI Feedback, Positioning

- **[Y. Sheng et al.](https://arxiv.org/abs/2507.05938)**
  - **Paper Title**: `Wireless Foundation Model for Multitask Learning`
  - **Paper Authors**: `Yucheng Sheng, Jiacheng Wang, Xingyu Zhou, Le Liang, Hao Ye, Shi Jin, Geoffrey Ye Li`
  - **Downstream Tasks**: Channel Extrapolation(time), Angle Prediction, Traffic Prediction

- **[WirelessGPT](https://arxiv.org/abs/2502.06877)**
  - **Paper Title**: `WirelessGPT: A Generative Pre-trained Multi-task Learning Framework for Wireless Communication`
  - **Paper Authors**: `Tingting Yang, Ping Zhang, Mengfan Zheng, Yuxuan Shi, Liwen Jing, Jianbo Huang, Nan Li`
  - **Downstream Tasks**: Channel Estimation, Channel Extrapolation(time), Pose Recognition

- **[BERT4MIMO](https://arxiv.org/abs/2501.01802)**
  - **Paper Title**: `BERT4MIMO: A Foundation Model using BERT Architecture for Massive MIMO Channel State Information Prediction`
  - **Paper Authors**: `Ferhat Ozgur Catak, Murat Kuzlu, Umit Cali`
  - **Downstream Tasks**: Channel Reconstruction

- **[WiFo](https://arxiv.org/abs/2412.08908)**
  - **Paper Title**: `WiFo: Wireless Foundation Model for Channel Prediction`
  - **Paper Authors**: `Boxun Liu, Shijian Gao, Xuanyu Liu, Xiang Cheng, Liuqing Yang`
  - **Downstream Tasks**: Channel Extrapolation(time, freq)

- **[LWM](https://arxiv.org/abs/2411.08872)**
  - **Paper Title**: `Large Wireless Model (LWM): A Foundation Model for Wireless Channels`
  - **Paper Authors**: `Sadjad Alikhani, Gouranga Charan, Ahmed Alkhateeb`
  - **Downstream Tasks**: Robust Beamforming, LOS/NLOS Identification, Sub-6 to mmWave Beam Prediction

- **[J. Ott et al.](https://arxiv.org/abs/2410.00617)**
  - **Paper Title**: `Radio Foundation Models: Pre-training Transformers for 5G-based Indoor Localization`
  - **Paper Authors**: `Jonathan Ott, Jonas Pirkl, Maximilian Stahlke, Tobias Feigl, Christopher Mutschler`
  - **Downstream Tasks**: Positioning



### IQ-based

- **[LWM-Spectro](https://arxiv.org/abs/2601.08780)**
  - **Paper Title**: `LWM-Spectro: A Foundation Model for Wireless Baseband Signal Spectrograms`
  - **Paper Authors**: `Namhyun Kim, Sadjad Alikhani, Ahmed Alkhateeb`
  - **Downstream Tasks**: Modulation Classification, Joint SNR and Doppler Classification


- **[SpectrumFM](https://arxiv.org/abs/2505.06256)**
  - **Paper Title**: `SpectrumFM: A Foundation Model for Intelligent Spectrum Management`
  - **Paper Authors**: `Fuhui Zhou, Chunyu Liu, Hao Zhang, Wei Wu, Qihui Wu, Derrick Wing Kwan Ng, Tony Q. S. Quek, Chan-Byoung Chae`
  - **Downstream Tasks**: Spectrum Sensing, Anomaly Detection, Wireless Technology Classification

- **[A. Abo et al.](https://arxiv.org/abs/2411.09996)**
  - **Paper Title**: `Building 6G Radio Foundation Models with Transformer Architectures`
  - **Paper Authors**: `Ahmed Aboulfotouh, Ashkan Eshaghbeigi, Hatem Abou-Zeid`
  - **Downstream Tasks**: Human Activity Sensing, Spectrogram Segmentation

### Others

- **[6G WavesFM](https://arxiv.org/abs/2504.14100)**
  - **Paper Title**: `6G WavesFM: A Foundation Model for Sensing, Communication, and Localization`
  - **Paper Authors**: `Ahmed Aboulfotouh, Elsayed Mohammed, Hatem Abou-Zeid`
  - **Input Modalities**: CSI, IQ
  - **Downstream Tasks**: Positioning, Channel Estimation, RF Signal Classification, Human Activity Sensing

## Discriminative Pretraining Approaches

### CSI-based

- **[CSI2Vec](https://arxiv.org/abs/2506.05237)**
  - **Paper Title**: `CSI2Vec: Towards a Universal CSI Feature Representation for Positioning and Channel Charting`
  - **Paper Authors**: `Victoria Palhares, Sueda Taner, Christoph Studer`
  - **Downstream Tasks**: Positioning

- **[CSI-CLIP](https://arxiv.org/abs/2502.11965)**
  - **Paper Title**: `A MIMO Wireless Channel Foundation Model via CIR-CSI Consistency`
  - **Paper Authors**: `Jun Jiang, Wenjun Yu, Yunfan Li, Yuan Gao, Shugong Xu`
  - **Downstream Tasks**: LOS/NLOS Identification, Beam Prediction, Positioning

### IQ-based

- **[O. Kanu](https://arxiv.org/abs/2509.03077)**
  - **Paper Title**: `Self-supervised Radio Representation Learning: Can we Learn Multiple Tasks?`
  - **Paper Authors**: `Ogechukwu Kanu, Ashkan Eshaghbeigi, Hatem Abou-Zeid`
  - **Downstream Tasks**: AoA Estimation, Automatic Modulation Classification

- **[IQFM](https://arxiv.org/abs/2506.06718)**
  - **Paper Title**: `IQFM: A Wireless Foundational Model for IQ Streams in AI-Native 6G`
  - **Paper Authors**: `Omar Mashaal, Hatem Abou-Zeid`
  - **Downstream Tasks**: Modulation Classification, AoA Estimation, Beam Prediction, RF fingerprinting

## Other Pretraining Approaches

- **[WWM](https://arxiv.org/abs/2603.25216)**
  - **Paper Title**: `A Wireless World Model for AI-Native 6G Networks`
  - **Paper Authors**: `Ziqi Chen, Yi Ren, Yixuan Huang, Qi Sun, Nan Li, Yuhong Huang, Chih-Lin I, Yifan Li, Liang Xia`
  - **Input Modalities**: CSI, Point Cloud, Trajectory
  - **Downstream Tasks**: Beam Prediction, Positioning, Channel Extrapolation(time, freq), CSI Feedback
  

- **[AM-FM](https://arxiv.org/abs/2602.11200)**
  - **Paper Title**: `AM-FM: A Foundation Model for Ambient Intelligence Through WiFi`
  - **Paper Authors**: `Guozhen Zhu, Yuqian Hu, Sakila Jayaweera, Weihang Gao, Wei-Hsiang Wang, Jiaxuan Zhang, Beibei Wang, Chenshu Wu, K. J. Ray Liu`
  - **Downstream Tasks**: Fall Detection, Human Activity Recognition, Gesture Recognition, User Identification, Positioning, Motion Source Recognition, Occupancy Detection, Proximity Estimation, WiFi Imaging.

- **[WirelessJEPA](https://arxiv.org/abs/2601.20190)**
  - **Paper Title**: `WirelessJEPA: A Multi-Antenna Foundation Model using Spatio-temporal Wireless Latent Predictions`
  - **Paper Authors**: `Viet Chu, Omar Mashaal, Hatem Abou-Zeid`
  - **Downstream Tasks**: Modulation Classification, AoA Estimation, GNSS jamming, RF fingerprinting, Protocol Classification, Interference Classification

- **[M.Cheraghinia](https://arxiv.org/abs/2505.19390)**
  - **Paper Title**: `A Unified Foundation Model for Wireless Technology Recognition and Localization`
  - **Paper Authors**: `Mohammad Cheraghinia, Eli De Poorter, Jaron Fontaine, Merouane Debbah, Adnan Shahid`
  - **Input Modalities**: CIR, IQ
  - **Downstream Tasks**: Wireless Technology Recognition, LOS/NLOS Identification, Ranging Error Correction

- **[LWLM](https://arxiv.org/abs/2505.10134)**
  - **Paper Title**: `Large Wireless Localization Model (LWLM): A Foundation Model for Positioning in 6G Networks`
  - **Paper Authors**: `Guangjin Pan, Kaixuan Huang, Hui Chen, Shunqing Zhang, Christian Häger, Henk Wymeersch`
  - **Downstream Tasks**: ToA Estimation, AoA Estimation, Positioning

- **[ContraWiMAE](https://arxiv.org/abs/2505.09160)**
  - **Paper Title**: `A Multi-Task Foundation Model for Wireless Channel Representation Using Contrastive and Masked Autoencoder Learning`
  - **Paper Authors**: `Berkay Guler, Giovanni Geraci, Hamid Jafarkhani`
  - **Downstream Tasks**: Cross-Frequency Beam Prediction, LOS/NLOS Identification, Channel Estimation

- **[T. Jiao et al.](https://arxiv.org/abs/2504.04797)**
  - **Paper Title**: `Addressing the Curse of Scenario and Task Generalization in AI-6G: A Multi-Modal Paradigm`
  - **Paper Authors**: `T. Jiao, et al.`
  - **Input Modalities**: CSI, environment
  - **Downstream Tasks**: CSI Feedback, Positioning, Beam Prediction, LOS/NLOS Identification

## Multitask Pretraining Approaches

- **[MUSE-FM](https://arxiv.org/abs/2509.01967)**
  - **Paper Title**: `MUSE-FM: Multi-task Environment-aware Foundation Model for Wireless Communications`
  - **Paper Authors**: `Tianyue Zheng, Jiajia Guo, Linglong Dai, Shi Jin, Jun Zhang`
  - **Input Modalities**: CSI, environment, received symbols
  - **Downstream Tasks**: Channel Estimation, MIMO Precoding, MIMO Detection, Channel Decoding, Positioning

## License

This work is licensed under the Creative Commons Attribution 4.0 International License (CC BY 4.0).

You are free to: share, copy, distribute, transmit, and adapt the work, as long as you attribute the original work to the maintainers of this list.
