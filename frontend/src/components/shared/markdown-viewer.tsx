import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";

export function MarkdownViewer({ content, className }: { content: string; className?: string }) {
  return (
    <div
      className={cn(
        "prose-saira max-w-none text-[0.95rem] leading-relaxed text-ink",
        className
      )}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: (props) => <h1 className="font-display text-2xl font-semibold mt-8 mb-3 first:mt-0" {...props} />,
          h2: (props) => <h2 className="font-display text-xl font-semibold mt-7 mb-2.5 first:mt-0" {...props} />,
          h3: (props) => <h3 className="font-display text-lg font-medium mt-5 mb-2" {...props} />,
          p: (props) => <p className="mb-4 text-ink-soft" {...props} />,
          ul: (props) => <ul className="mb-4 ml-5 list-disc space-y-1.5 text-ink-soft" {...props} />,
          ol: (props) => <ol className="mb-4 ml-5 list-decimal space-y-1.5 text-ink-soft" {...props} />,
          strong: (props) => <strong className="font-semibold text-ink" {...props} />,
          em: (props) => <em className="font-display italic" {...props} />,
          blockquote: (props) => (
            <blockquote className="my-4 border-l-2 border-teal-500 pl-4 italic text-ink-soft" {...props} />
          ),
          code: (props) => (
            <code className="rounded bg-paper-dim px-1.5 py-0.5 font-mono text-[0.85em] text-teal-700" {...props} />
          ),
          a: (props) => <a className="text-teal-700 underline underline-offset-2" {...props} />,
          hr: () => <div className="trail-line my-6" />,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
