import { Paper, Project, Note, ChatMessage, User } from "./types";

export const currentUser: User = {
  name: "Meera Anand",
  email: "meera.anand@stanford.edu",
  role: "PhD Candidate, Computer Science",
  institution: "Stanford University",
  avatarInitial: "M",
};

export const papers: Paper[] = [
  {
    id: "p1",
    title: "Attention Is All You Need",
    authors: [
      { name: "A. Vaswani" },
      { name: "N. Shazeer" },
      { name: "N. Parmar" },
      { name: "J. Uszkoreit" },
    ],
    year: 2017,
    venue: "NeurIPS",
    source: "arXiv",
    abstract:
      "We propose the Transformer, a model architecture eschewing recurrence and instead relying entirely on an attention mechanism to draw global dependencies between input and output, allowing for significantly more parallelization.",
    citationCount: 128430,
    tags: ["transformers", "attention", "sequence modeling"],
    savedToProjectIds: ["proj1", "proj2"],
    readingStatus: "read",
    aiSummary: {
      tldr: "Introduces the Transformer architecture, replacing recurrence with self-attention for faster, more parallelizable sequence modeling.",
      keyFindings: [
        "Self-attention alone can outperform recurrent and convolutional models on translation tasks.",
        "Multi-head attention lets the model attend to information from different representation subspaces.",
        "Positional encodings inject sequence order without recurrence.",
      ],
      methodology:
        "Encoder-decoder architecture built entirely from stacked self-attention and point-wise feed-forward layers, trained on WMT translation datasets.",
      limitations: [
        "Quadratic memory cost in sequence length.",
        "Requires large amounts of training data to outperform recurrent baselines.",
      ],
    },
    extracted: {
      problem: "Sequence transduction relying on recurrence is slow to train and hard to parallelize.",
      dataset: ["WMT 2014 English-German", "WMT 2014 English-French"],
      method: "Self-attention encoder-decoder (Transformer)",
      metrics: [
        { name: "BLEU (EN-DE)", value: "28.4" },
        { name: "BLEU (EN-FR)", value: "41.8" },
      ],
      codeAvailable: true,
    },
  },
  {
    id: "p2",
    title: "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding",
    authors: [{ name: "J. Devlin" }, { name: "M. Chang" }, { name: "K. Lee" }],
    year: 2019,
    venue: "NAACL",
    source: "arXiv",
    abstract:
      "We introduce BERT, designed to pretrain deep bidirectional representations by jointly conditioning on both left and right context in all layers, obtaining state-of-the-art results on eleven NLP tasks.",
    citationCount: 98210,
    tags: ["pretraining", "language models", "nlp"],
    savedToProjectIds: ["proj1"],
    readingStatus: "reading",
    aiSummary: {
      tldr: "Pretrains a bidirectional Transformer encoder using masked language modeling, then fine-tunes it on downstream NLP tasks.",
      keyFindings: [
        "Bidirectional context during pretraining beats left-to-right language modeling for understanding tasks.",
        "Masked language modeling plus next-sentence prediction gives strong transferable representations.",
        "A single pretrained model can be fine-tuned across eleven diverse NLP benchmarks.",
      ],
      methodology:
        "Masked language modeling and next-sentence prediction over BooksCorpus and English Wikipedia, followed by task-specific fine-tuning.",
      limitations: [
        "Pretraining is computationally expensive.",
        "Fixed input length limits use on long documents.",
      ],
    },
    extracted: {
      problem: "Prior language representations were unidirectional, limiting the architectures usable in pretraining.",
      dataset: ["BooksCorpus", "English Wikipedia"],
      method: "Masked language modeling (BERT)",
      metrics: [
        { name: "GLUE score", value: "80.5" },
        { name: "SQuAD 1.1 F1", value: "93.2" },
      ],
      codeAvailable: true,
    },
  },
  {
    id: "p3",
    title: "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
    authors: [{ name: "P. Lewis" }, { name: "E. Perez" }, { name: "A. Piktus" }],
    year: 2020,
    venue: "NeurIPS",
    source: "arXiv",
    abstract:
      "We explore a general-purpose fine-tuning recipe for retrieval-augmented generation models which combine pre-trained parametric and non-parametric memory for language generation.",
    citationCount: 12480,
    tags: ["retrieval", "generation", "nlp"],
    savedToProjectIds: ["proj2"],
    readingStatus: "unread",
    aiSummary: {
      tldr: "Combines a pretrained seq2seq model with a dense vector index of Wikipedia, retrieved at generation time, to ground outputs in evidence.",
      keyFindings: [
        "Retrieval-augmented models produce more specific and factual text than purely parametric models.",
        "The non-parametric memory can be swapped without retraining the generator.",
        "RAG sets a new state of the art on several open-domain QA benchmarks.",
      ],
      methodology:
        "A dense passage retriever selects supporting documents, which condition a BART-based generator; both are fine-tuned end-to-end.",
      limitations: [
        "Retrieval quality bounds overall answer quality.",
        "Latency overhead from the retrieval step.",
      ],
    },
    extracted: {
      problem: "Purely parametric language models struggle to access and update precise factual knowledge.",
      dataset: ["Natural Questions", "TriviaQA", "Wikipedia dump"],
      method: "Retrieval-Augmented Generation (RAG)",
      metrics: [
        { name: "Natural Questions EM", value: "44.5" },
        { name: "TriviaQA EM", value: "68.0" },
      ],
      codeAvailable: true,
    },
  },
  {
    id: "p4",
    title: "LoRA: Low-Rank Adaptation of Large Language Models",
    authors: [{ name: "E. Hu" }, { name: "Y. Shen" }, { name: "P. Wallis" }],
    year: 2021,
    venue: "ICLR",
    source: "arXiv",
    abstract:
      "We propose Low-Rank Adaptation, which freezes pretrained model weights and injects trainable rank decomposition matrices into each layer, greatly reducing trainable parameters for downstream tasks.",
    citationCount: 8760,
    tags: ["fine-tuning", "efficiency", "llm"],
    savedToProjectIds: ["proj1"],
    readingStatus: "unread",
    aiSummary: {
      tldr: "Freezes the base model and trains small low-rank update matrices per layer, cutting fine-tuning cost with little quality loss.",
      keyFindings: [
        "Trainable parameters can be reduced by 10,000x compared to full fine-tuning.",
        "No added inference latency since low-rank matrices merge into existing weights.",
        "Performs comparably to full fine-tuning on GPT-3 scale models.",
      ],
      methodology:
        "Decomposes weight updates into two low-rank matrices trained on top of a frozen pretrained backbone.",
      limitations: [
        "Rank choice requires task-specific tuning.",
        "Gains diminish on tasks needing broad representational shifts.",
      ],
    },
    extracted: {
      problem: "Full fine-tuning of large language models is costly in memory and storage per task.",
      dataset: ["GLUE", "WikiSQL", "SAMSum"],
      method: "Low-rank adaptation (LoRA)",
      metrics: [
        { name: "GLUE avg", value: "89.1" },
        { name: "Trainable params", value: "0.01%" },
      ],
      codeAvailable: true,
    },
  },
  {
    id: "p5",
    title: "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models",
    authors: [{ name: "J. Wei" }, { name: "X. Wang" }, { name: "D. Schuurmans" }],
    year: 2022,
    venue: "NeurIPS",
    source: "arXiv",
    abstract:
      "We show that generating a chain of thought — a series of intermediate reasoning steps — significantly improves the ability of large language models to perform complex reasoning.",
    citationCount: 6320,
    tags: ["reasoning", "prompting", "llm"],
    savedToProjectIds: [],
    readingStatus: "unread",
    aiSummary: {
      tldr: "Prompting a large model with a few chain-of-thought exemplars sharply improves multi-step reasoning accuracy.",
      keyFindings: [
        "Chain-of-thought prompting emerges only at sufficient model scale.",
        "Gains are largest on arithmetic, commonsense, and symbolic reasoning tasks.",
        "No fine-tuning is required — the effect is purely a prompting-time behavior.",
      ],
      methodology:
        "Few-shot prompting with exemplars that include manually written intermediate reasoning steps before the final answer.",
      limitations: [
        "Effect is unreliable in smaller models.",
        "Correct-looking chains can still lead to wrong answers.",
      ],
    },
    extracted: {
      problem: "Large language models struggle with multi-step arithmetic and logical reasoning under standard prompting.",
      dataset: ["GSM8K", "SVAMP", "CommonsenseQA"],
      method: "Chain-of-thought few-shot prompting",
      metrics: [
        { name: "GSM8K accuracy", value: "56.9%" },
      ],
      codeAvailable: false,
    },
  },
  {
    id: "p6",
    title: "Denoising Diffusion Probabilistic Models",
    authors: [{ name: "J. Ho" }, { name: "A. Jain" }, { name: "P. Abbeel" }],
    year: 2020,
    venue: "NeurIPS",
    source: "arXiv",
    abstract:
      "We present high quality image synthesis results using diffusion probabilistic models, a class of latent variable models inspired by nonequilibrium thermodynamics.",
    citationCount: 15920,
    tags: ["diffusion", "generative models", "vision"],
    savedToProjectIds: ["proj2"],
    readingStatus: "read",
    aiSummary: {
      tldr: "Trains a model to reverse a fixed noising process step by step, producing a strong generative model for images.",
      keyFindings: [
        "A reweighted variational bound gives the best sample quality.",
        "Diffusion models can match or beat GANs on sample fidelity metrics.",
        "Progressive denoising connects naturally to autoregressive decoding and score matching.",
      ],
      methodology:
        "A Markov chain gradually adds Gaussian noise to data; a neural network is trained to predict and remove that noise at each step.",
      limitations: [
        "Sampling requires many sequential steps, making inference slow.",
        "Sensitive to the choice of noise schedule.",
      ],
    },
    extracted: {
      problem: "Existing generative models trade off sample quality, diversity, and training stability.",
      dataset: ["CIFAR-10", "LSUN"],
      method: "Denoising diffusion probabilistic models (DDPM)",
      metrics: [
        { name: "CIFAR-10 FID", value: "3.17" },
      ],
      codeAvailable: true,
    },
  },
  {
    id: "p7",
    title: "A Survey of Large Language Models",
    authors: [{ name: "W. X. Zhao" }, { name: "K. Zhou" }, { name: "J. Li" }],
    year: 2023,
    venue: "arXiv preprint",
    source: "arXiv",
    abstract:
      "This survey reviews the recent advances of large language models, covering pre-training, adaptation, utilization, and evaluation, along with available resources and remaining challenges.",
    citationCount: 3140,
    tags: ["survey", "llm"],
    savedToProjectIds: [],
    readingStatus: "unread",
    aiSummary: {
      tldr: "A structured survey of LLM pretraining, adaptation, and evaluation techniques, with a catalog of public resources.",
      keyFindings: [
        "Scaling laws roughly predict downstream performance from compute, data, and parameters.",
        "Instruction tuning and RLHF are now the dominant adaptation strategies.",
        "Evaluation remains fragmented across benchmarks with inconsistent protocols.",
      ],
      methodology: "Literature synthesis across pretraining, adaptation, utilization and evaluation of LLMs.",
      limitations: [
        "Fast-moving field means coverage becomes dated quickly.",
        "Some claims rely on vendor-reported benchmark numbers.",
      ],
    },
    extracted: {
      problem: "The literature on large language models is large and fragmented across subfields.",
      dataset: [],
      method: "Structured literature survey",
      metrics: [],
      codeAvailable: false,
    },
  },
  {
    id: "p8",
    title: "Deep Residual Learning for Image Recognition",
    authors: [{ name: "K. He" }, { name: "X. Zhang" }, { name: "S. Ren" }],
    year: 2016,
    venue: "CVPR",
    source: "IEEE",
    abstract:
      "We present a residual learning framework to ease the training of networks substantially deeper than those used previously, reformulating layers as learning residual functions.",
    citationCount: 178200,
    tags: ["vision", "cnn", "residual learning"],
    savedToProjectIds: [],
    readingStatus: "unread",
    aiSummary: {
      tldr: "Introduces residual (skip) connections that make very deep convolutional networks trainable.",
      keyFindings: [
        "Residual connections resolve the degradation problem seen in very deep plain networks.",
        "152-layer ResNets outperform shallower networks while remaining easier to optimize.",
        "The approach generalizes well to detection and localization tasks.",
      ],
      methodology: "Stacked residual blocks with identity shortcut connections, trained on ImageNet.",
      limitations: ["Very deep variants still carry high computational cost."],
    },
    extracted: {
      problem: "Very deep networks are hard to optimize and can perform worse than shallower ones.",
      dataset: ["ImageNet", "CIFAR-10"],
      method: "Residual networks (ResNet)",
      metrics: [{ name: "ImageNet top-5 error", value: "3.57%" }],
      codeAvailable: true,
    },
  },
];

export const projects: Project[] = [
  {
    id: "proj1",
    name: "Efficient Fine-Tuning Methods",
    description:
      "Surveying parameter-efficient fine-tuning techniques for large language models ahead of the qualifying exam.",
    createdAt: "2026-05-02",
    updatedAt: "2026-07-14",
    color: "teal",
    paperIds: ["p1", "p2", "p4"],
    collaborators: [
      { name: "Meera Anand", avatarInitial: "M" },
      { name: "Kabir Rao", avatarInitial: "K" },
    ],
    milestones: {
      papersAdded: true,
      notesTaken: true,
      compared: true,
      reviewGenerated: false,
    },
  },
  {
    id: "proj2",
    name: "Retrieval & Generative Grounding",
    description:
      "Comparing retrieval-augmented approaches against diffusion-based generative baselines for grounded generation.",
    createdAt: "2026-06-10",
    updatedAt: "2026-07-18",
    color: "brass",
    paperIds: ["p1", "p3", "p6"],
    collaborators: [{ name: "Meera Anand", avatarInitial: "M" }],
    milestones: {
      papersAdded: true,
      notesTaken: false,
      compared: false,
      reviewGenerated: false,
    },
  },
  {
    id: "proj3",
    name: "Thesis Chapter 2 — Related Work",
    description: "Background reading and synthesis for the related-work chapter of the dissertation.",
    createdAt: "2026-04-20",
    updatedAt: "2026-07-05",
    color: "ink",
    paperIds: [],
    collaborators: [{ name: "Meera Anand", avatarInitial: "M" }],
    milestones: {
      papersAdded: false,
      notesTaken: false,
      compared: false,
      reviewGenerated: false,
    },
  },
];

export const notes: Note[] = [
  {
    id: "n1",
    paperId: "p1",
    content: "Multi-head attention — worth comparing head count vs. BLEU ablation in section 6.",
    highlight: "Multi-head attention allows the model to jointly attend to information from different representation subspaces.",
    createdAt: "2026-07-10",
  },
  {
    id: "n2",
    paperId: "p1",
    content: "Good motivating citation for why recurrence limits parallelization — use in intro.",
    createdAt: "2026-07-11",
  },
  {
    id: "n3",
    paperId: "p2",
    content: "Check whether the next-sentence-prediction objective was later shown to be unnecessary (RoBERTa ablation).",
    createdAt: "2026-07-12",
  },
];

export const chatMessages: ChatMessage[] = [
  {
    id: "c1",
    role: "user",
    content: "How does LoRA compare to full fine-tuning in terms of memory footprint?",
    createdAt: "2026-07-15T09:12:00",
  },
  {
    id: "c2",
    role: "assistant",
    content:
      "Across the papers in this project, LoRA freezes the pretrained weights and only trains small low-rank update matrices, cutting trainable parameters by roughly four orders of magnitude compared to full fine-tuning, with no extra inference latency since the updates merge back into the original weights.",
    citedPaperIds: ["p4"],
    createdAt: "2026-07-15T09:12:20",
  },
  {
    id: "c3",
    role: "user",
    content: "Does the Transformer paper discuss anything about parameter efficiency?",
    createdAt: "2026-07-15T09:14:00",
  },
  {
    id: "c4",
    role: "assistant",
    content:
      "Not directly — Attention Is All You Need focuses on replacing recurrence with self-attention for parallelization and translation quality, not parameter efficiency. LoRA builds on top of Transformer-style architectures rather than modifying that concern.",
    citedPaperIds: ["p1", "p4"],
    createdAt: "2026-07-15T09:14:18",
  },
];

export function getPaperById(id: string) {
  return papers.find((p) => p.id === id);
}

export function getProjectById(id: string) {
  return projects.find((p) => p.id === id);
}

export function getPapersForProject(projectId: string) {
  const project = getProjectById(projectId);
  if (!project) return [];
  return papers.filter((p) => project.paperIds.includes(p.id));
}

export function getNotesForPaper(paperId: string) {
  return notes.filter((n) => n.paperId === paperId);
}

export function similarPapers(paperId: string, count = 3) {
  return papers.filter((p) => p.id !== paperId).slice(0, count);
}
