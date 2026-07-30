import Link from "next/link";
import {
  Search,
  FolderKanban,
  GitCompareArrows,
  Sparkles,
  BookMarked,
  NotebookPen,
  ArrowRight,
} from "lucide-react";
import { MarketingNavbar } from "@/components/layout/marketing-navbar";
import { HeroIllustration } from "@/components/shared/hero-illustration";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { TrailDivider } from "@/components/shared/trail-divider";

const sources = ["arXiv", "Semantic Scholar", "PubMed", "IEEE Xplore", "ACL Anthology", "CORE"];

const features = [
  {
    icon: Search,
    title: "Search across every source",
    body: "One query reaches arXiv, Semantic Scholar, PubMed, and more — ranked and de-duplicated for you.",
  },
  {
    icon: FolderKanban,
    title: "Organize into projects",
    body: "Group papers by thesis chapter, grant, or question. Every project keeps its own trail of progress.",
  },
  {
    icon: Sparkles,
    title: "Ask questions across papers",
    body: "SAIRA reads the full text of your saved papers and answers with citations back to the source.",
  },
  {
    icon: GitCompareArrows,
    title: "Compare side by side",
    body: "Line up methods, datasets, and results across papers to see where they agree — and where they don't.",
  },
  {
    icon: NotebookPen,
    title: "Notes stay with the paper",
    body: "Highlight a passage, leave a note, and find it again instantly from the paper or the project.",
  },
  {
    icon: BookMarked,
    title: "Draft your literature review",
    body: "Generate a structured first draft from your saved papers, with citations you can verify in one click.",
  },
];

export default function LandingPage() {
  return (
    <div className="flex min-h-screen flex-col bg-paper">
      <MarketingNavbar />

      {/* Hero */}
      <section className="mx-auto w-full max-w-6xl px-5 pb-6 pt-14 md:px-8 md:pt-20" id="product">
        <div className="mx-auto max-w-2xl text-center">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-3 py-1 text-xs font-medium text-ink-soft">
            <Sparkles className="h-3 w-3 text-teal-600" />
            Smart AI Research Assistant
          </span>
          <h1 className="mt-5 font-display text-4xl font-medium leading-[1.1] text-ink sm:text-5xl">
            A research trail through <em className="italic text-teal-700">every</em> paper you read.
          </h1>
          <p className="mx-auto mt-5 max-w-lg text-base leading-relaxed text-ink-soft">
            Literature reviews rarely move in a straight line. SAIRA helps you search, organize,
            compare, and synthesize papers — so you always know where you are on the trail.
          </p>
          <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link href="/login">
              <Button size="lg" className="gap-2">
                Start your trail
                <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
            <a href="#how-it-works">
              <Button size="lg" variant="outline">
                See how it works
              </Button>
            </a>
          </div>
        </div>

        <div className="mt-14">
          <HeroIllustration />
        </div>

        <div className="mt-10 text-center">
          <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">
            Searches across
          </p>
          <div className="mt-4 flex flex-wrap items-center justify-center gap-x-8 gap-y-3">
            {sources.map((s) => (
              <span key={s} className="font-display text-sm text-ink-faint">
                {s}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="mx-auto w-full max-w-5xl px-5 py-20 md:px-8">
        <Card className="grid gap-0 overflow-hidden md:grid-cols-2">
          <div className="flex flex-col justify-center gap-4 p-8 md:p-12">
            <span className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-brass-100">
              <BookMarked className="h-4.5 w-4.5 text-brass-600" />
            </span>
            <h2 className="font-display text-2xl font-medium leading-snug text-ink sm:text-3xl">
              Find your way through the literature
            </h2>
            <p className="text-[0.95rem] leading-relaxed text-ink-soft">
              Every project you start is its own path: papers you save, notes you take, and the
              questions you ask are always in the same place. When you're ready, SAIRA drafts a
              literature review from what you've gathered — with every claim traceable back to a
              source.
            </p>
            <div>
              <Link href="/login">
                <Button variant="secondary" className="gap-1.5">
                  Try it with a project
                  <ArrowRight className="h-3.5 w-3.5" />
                </Button>
              </Link>
            </div>
          </div>
          <div className="flex items-center justify-center bg-paper-dim p-8 md:p-12">
            <div className="w-full max-w-sm rounded-xl border border-line bg-surface p-5 shadow-sm">
              <div className="mb-4 flex items-center justify-between">
                <p className="text-xs font-medium text-ink-faint">Project trail</p>
                <span className="font-mono text-[11px] text-ink-faint">3/4</span>
              </div>
              <ul className="space-y-3 text-sm">
                <li className="flex items-center gap-2 text-ink">
                  <span className="h-2 w-2 rounded-full bg-teal-600" /> Papers added
                </li>
                <li className="flex items-center gap-2 text-ink">
                  <span className="h-2 w-2 rounded-full bg-teal-600" /> Notes taken
                </li>
                <li className="flex items-center gap-2 text-ink">
                  <span className="h-2 w-2 rounded-full bg-teal-600" /> Papers compared
                </li>
                <li className="flex items-center gap-2 text-ink-faint">
                  <span className="h-2 w-2 rounded-full border border-line" /> Review generated
                </li>
              </ul>
            </div>
          </div>
        </Card>
      </section>

      {/* Features */}
      <section id="features" className="mx-auto w-full max-w-6xl px-5 pb-20 md:px-8">
        <div className="mx-auto mb-10 max-w-lg text-center">
          <h2 className="font-display text-3xl font-medium text-ink">Everything the review needs</h2>
          <p className="mt-2 text-sm text-ink-soft">
            Six tools that stay out of the way until you need them.
          </p>
        </div>
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((f) => (
            <Card key={f.title} className="p-6">
              <span className="mb-4 inline-flex h-10 w-10 items-center justify-center rounded-full bg-teal-50">
                <f.icon className="h-4.5 w-4.5 text-teal-600" />
              </span>
              <h3 className="font-display text-lg font-medium text-ink">{f.title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-ink-soft">{f.body}</p>
            </Card>
          ))}
        </div>
      </section>

      <TrailDivider className="mx-auto max-w-4xl" />

      {/* Closing CTA */}
      <section className="mx-auto w-full max-w-3xl px-5 py-20 text-center md:px-8">
        <h2 className="font-display text-3xl font-medium text-ink sm:text-4xl">
          Your next literature review starts on the trail.
        </h2>
        <p className="mx-auto mt-3 max-w-md text-sm text-ink-soft">
          Free to try. No credit card, no setup — just your first search.
        </p>
        <div className="mt-7">
          <Link href="/login">
            <Button size="lg" className="gap-2">
              Start your trail <ArrowRight className="h-4 w-4" />
            </Button>
          </Link>
        </div>
      </section>

      <footer className="border-t border-line px-5 py-8 md:px-8">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 sm:flex-row">
          <p className="text-xs text-ink-faint">© 2026 SAIRA. All rights reserved.</p>
          <div className="flex gap-5 text-xs text-ink-faint">
            <span>Privacy</span>
            <span>Terms</span>
            <span>Contact</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
