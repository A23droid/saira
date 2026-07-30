"use client";

import { useRef, useState } from "react";
import { User, Bell, Palette, Plug, KeyRound, Trash2, Loader2, Check } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/contexts/auth-context";
import { ApiError } from "@/lib/api/client";

const sections = [
  { id: "profile", label: "Profile", icon: User },
  { id: "notifications", label: "Notifications", icon: Bell },
  { id: "appearance", label: "Appearance", icon: Palette },
  { id: "integrations", label: "Integrations", icon: Plug },
  { id: "security", label: "Security", icon: KeyRound },
];

const providerLabel: Record<string, string> = {
  local: "Email & password",
  google: "Google",
  orcid: "ORCID",
};

const MAX_AVATAR_MB = 5;
const ALLOWED_AVATAR_TYPES = ["image/jpeg", "image/png", "image/webp"];

export default function SettingsPage() {
  const [active, setActive] = useState("profile");
  const [notifs, setNotifs] = useState({ digest: true, mentions: true, product: false });
  const { user, updateProfile, uploadAvatar } = useAuth();

  const [name, setName] = useState(user?.name ?? "");
  const [savingName, setSavingName] = useState(false);
  const [nameError, setNameError] = useState<string | null>(null);
  const [nameSaved, setNameSaved] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [avatarError, setAvatarError] = useState<string | null>(null);

  if (!user) return null;

  async function handleSaveName() {
    setNameError(null);
    setNameSaved(false);
    setSavingName(true);
    try {
      await updateProfile(name.trim());
      setNameSaved(true);
      setTimeout(() => setNameSaved(false), 2500);
    } catch (err) {
      setNameError(err instanceof ApiError ? err.message : "Couldn't save your changes.");
    } finally {
      setSavingName(false);
    }
  }

  function handlePhotoButtonClick() {
    fileInputRef.current?.click();
  }

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-selecting the same file later
    if (!file) return;

    setAvatarError(null);

    if (!ALLOWED_AVATAR_TYPES.includes(file.type)) {
      setAvatarError("Please choose a JPG, PNG, or WebP image.");
      return;
    }
    if (file.size > MAX_AVATAR_MB * 1024 * 1024) {
      setAvatarError(`Images must be under ${MAX_AVATAR_MB}MB.`);
      return;
    }

    setUploading(true);
    try {
      await uploadAvatar(file);
    } catch (err) {
      setAvatarError(err instanceof ApiError ? err.message : "Upload failed. Please try again.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div>
      <PageHeader title="Settings" subtitle="Manage your account, preferences, and connections." />

      <div className="grid gap-6 lg:grid-cols-4">
        <nav className="flex gap-1 overflow-x-auto lg:col-span-1 lg:flex-col lg:overflow-visible">
          {sections.map((s) => (
            <button
              key={s.id}
              onClick={() => setActive(s.id)}
              className={`flex shrink-0 items-center gap-2.5 rounded-xl px-3.5 py-2.5 text-left text-sm font-medium transition-colors ${
                active === s.id ? "bg-surface text-ink shadow-sm border border-line" : "text-ink-soft hover:bg-paper-dim"
              }`}
            >
              <s.icon className={`h-4 w-4 ${active === s.id ? "text-teal-600" : "text-ink-faint"}`} />
              {s.label}
            </button>
          ))}
        </nav>

        <div className="lg:col-span-3">
          {active === "profile" && (
            <Card className="p-6">
              <div className="mb-6 flex items-center gap-4">
                <Avatar className="h-16 w-16 border border-line">
                  {user.avatarUrl && <AvatarImage src={user.avatarUrl} alt={user.name} />}
                  <AvatarFallback className="text-xl">{user.avatarInitial}</AvatarFallback>
                </Avatar>
                <div>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    className="hidden"
                    onChange={handleFileChange}
                  />
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handlePhotoButtonClick}
                    disabled={uploading}
                    className="gap-1.5"
                  >
                    {uploading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    {uploading ? "Uploading…" : "Change photo"}
                  </Button>
                  <p className="mt-1.5 text-xs text-ink-faint">JPG, PNG, or WebP, up to {MAX_AVATAR_MB}MB.</p>
                  {avatarError && <p className="mt-1 text-xs text-danger">{avatarError}</p>}
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="fullname">Full name</Label>
                  <Input id="fullname" value={name} onChange={(e) => setName(e.target.value)} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="email">Email</Label>
                  <Input id="email" value={user.email} disabled />
                  <p className="text-xs text-ink-faint">Email can&apos;t be changed yet.</p>
                </div>
              </div>

              <Separator className="my-6" />

              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-4 text-sm text-ink-soft">
                  <span>
                    Sign-in method:{" "}
                    <Badge variant="secondary" className="ml-1">
                      {providerLabel[user.provider] ?? user.provider}
                    </Badge>
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  {nameError && <p className="text-sm text-danger">{nameError}</p>}
                  {nameSaved && (
                    <p className="flex items-center gap-1 text-sm text-teal-700">
                      <Check className="h-3.5 w-3.5" /> Saved
                    </p>
                  )}
                  <Button onClick={handleSaveName} disabled={savingName || !name.trim()}>
                    {savingName ? "Saving…" : "Save changes"}
                  </Button>
                </div>
              </div>
            </Card>
          )}

          {active === "notifications" && (
            <Card className="divide-y divide-line-soft p-0">
              <ToggleRow
                title="Weekly digest"
                description="A summary of new papers matching your saved searches."
                checked={notifs.digest}
                onChange={(v) => setNotifs((n) => ({ ...n, digest: v }))}
              />
              <ToggleRow
                title="Collaborator activity"
                description="When a collaborator adds a paper or note to a shared project."
                checked={notifs.mentions}
                onChange={(v) => setNotifs((n) => ({ ...n, mentions: v }))}
              />
              <ToggleRow
                title="Product updates"
                description="Occasional emails about new SAIRA features."
                checked={notifs.product}
                onChange={(v) => setNotifs((n) => ({ ...n, product: v }))}
              />
            </Card>
          )}

          {active === "appearance" && (
            <Card className="p-6">
              <p className="mb-4 text-sm font-medium text-ink">Theme</p>
              <div className="grid grid-cols-3 gap-3">
                {["Paper (default)", "Dim", "System"].map((theme, i) => (
                  <button
                    key={theme}
                    className={`rounded-xl border-2 p-4 text-left text-sm ${
                      i === 0 ? "border-teal-600" : "border-line"
                    }`}
                  >
                    <div className="mb-3 h-10 w-full rounded-lg bg-paper-dim" />
                    {theme}
                  </button>
                ))}
              </div>
              <p className="mt-4 text-xs text-ink-faint">
                Additional themes are on the roadmap — SAIRA currently uses the warm paper theme
                throughout.
              </p>
            </Card>
          )}

          {active === "integrations" && (
            <Card className="divide-y divide-line-soft p-0">
              {[
                { name: "Zotero", desc: "Sync saved papers to a Zotero library.", connected: true },
                { name: "Slack", desc: "Post project updates to a channel.", connected: false },
                { name: "Notion", desc: "Export literature reviews as Notion pages.", connected: false },
              ].map((integration) => (
                <div key={integration.name} className="flex items-center justify-between gap-4 p-5">
                  <div>
                    <p className="font-medium text-ink">{integration.name}</p>
                    <p className="text-sm text-ink-soft">{integration.desc}</p>
                  </div>
                  {integration.connected ? (
                    <Badge variant="secondary">Connected</Badge>
                  ) : (
                    <Button variant="outline" size="sm">
                      Connect
                    </Button>
                  )}
                </div>
              ))}
            </Card>
          )}

          {active === "security" && (
            <div className="flex flex-col gap-5">
              <Card className="p-6">
                <p className="mb-4 text-sm font-medium text-ink">Change password</p>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="current-pw">Current password</Label>
                    <Input id="current-pw" type="password" placeholder="••••••••" />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="new-pw">New password</Label>
                    <Input id="new-pw" type="password" placeholder="••••••••" />
                  </div>
                </div>
                <div className="mt-5 flex justify-end">
                  <Button>Update password</Button>
                </div>
              </Card>

              <Card className="border-danger-100 p-6">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="flex items-center gap-2 font-medium text-danger">
                      <Trash2 className="h-4 w-4" /> Delete account
                    </p>
                    <p className="mt-1 text-sm text-ink-soft">
                      Permanently deletes your projects, papers, and notes. This cannot be undone.
                    </p>
                  </div>
                  <Button variant="destructive" size="sm">
                    Delete account
                  </Button>
                </div>
              </Card>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ToggleRow({
  title,
  description,
  checked,
  onChange,
}: {
  title: string;
  description: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-4 p-5">
      <div>
        <p className="font-medium text-ink">{title}</p>
        <p className="text-sm text-ink-soft">{description}</p>
      </div>
      <Switch checked={checked} onCheckedChange={onChange} />
    </div>
  );
}
