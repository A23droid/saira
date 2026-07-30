"use client";

import { motion } from "framer-motion";

export function HeroIllustration() {
  return (
    <svg
      viewBox="0 0 1200 420"
      className="w-full"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <linearGradient id="skyGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#faf6ec" />
          <stop offset="100%" stopColor="#f3ede0" />
        </linearGradient>
      </defs>
      <rect width="1200" height="420" fill="url(#skyGrad)" rx="28" />

      {/* Rolling hills */}
      <path d="M0 300 Q 200 250 400 290 T 800 280 T 1200 300 V420 H0 Z" fill="#f0ead9" />
      <path d="M0 340 Q 250 300 500 335 T 1000 320 T 1200 340 V420 H0 Z" fill="#e7ded0" opacity="0.6" />

      {/* Dotted trail winding through the hills */}
      <motion.path
        d="M60 360 C 220 320, 260 260, 400 250 S 560 300, 650 260 S 820 180, 980 200 S 1080 150, 1140 110"
        fill="none"
        stroke="#c9bfa8"
        strokeWidth="3"
        strokeDasharray="1 14"
        strokeLinecap="round"
        initial={{ pathLength: 0, opacity: 0 }}
        animate={{ pathLength: 1, opacity: 1 }}
        transition={{ duration: 1.6, ease: "easeInOut" }}
      />

      {/* Paper nodes along the trail */}
      {[
        { x: 220, y: 300, label: "search" },
        { x: 480, y: 258, label: "read" },
        { x: 760, y: 235, label: "compare" },
      ].map((n, i) => (
        <motion.g
          key={n.label}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5 + i * 0.25, duration: 0.5 }}
        >
          <circle cx={n.x} cy={n.y} r="22" fill="#ffffff" stroke="#e7e0d2" strokeWidth="1.5" />
          <rect x={n.x - 8} y={n.y - 10} width="16" height="20" rx="2" fill="none" stroke="#12796b" strokeWidth="1.6" />
          <line x1={n.x - 5} y1={n.y - 4} x2={n.x + 5} y2={n.y - 4} stroke="#12796b" strokeWidth="1.2" />
          <line x1={n.x - 5} y1={n.y} x2={n.x + 5} y2={n.y} stroke="#12796b" strokeWidth="1.2" />
          <line x1={n.x - 5} y1={n.y + 4} x2={n.x + 2} y2={n.y + 4} stroke="#12796b" strokeWidth="1.2" />
        </motion.g>
      ))}

      {/* Destination compass */}
      <motion.g
        initial={{ opacity: 0, scale: 0.7 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 1.1, duration: 0.5 }}
      >
        <circle cx="1140" cy="110" r="34" fill="#ffffff" stroke="#a8792f" strokeWidth="1.6" />
        <circle cx="1140" cy="110" r="24" fill="none" stroke="#a8792f" strokeWidth="1.2" />
        <path d="M1140 96 L1147 110 L1140 124 L1133 110 Z" fill="#a8792f" />
      </motion.g>

      {/* Floating clouds */}
      <g opacity="0.7">
        <ellipse cx="140" cy="90" rx="46" ry="16" fill="#ffffff" />
        <ellipse cx="175" cy="82" rx="34" ry="14" fill="#ffffff" />
        <ellipse cx="900" cy="70" rx="50" ry="17" fill="#ffffff" />
        <ellipse cx="940" cy="60" rx="34" ry="13" fill="#ffffff" />
      </g>
    </svg>
  );
}
