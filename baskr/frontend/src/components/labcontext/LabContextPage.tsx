// Lab Context settings page (handoff "Lab Context Page").
// Companion to the Research Dashboard welcome screen — lets a user give the
// system background about their lab: reference documents, open questions, and
// miscellaneous notes. Two-column settings layout under the shared top nav.
import { useRef, useState } from "react";
import TopNav from "../welcome/TopNav";

// A file the user has staged for upload. We hold the File handle so Save can
// POST the actual bytes; name/size are cached for rendering the chip.
interface StagedFile {
  id: string;
  name: string;
  size: number;
  file: File;
}

// B / KB / MB — handoff §"Size formatting".
function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

const sectionEyebrow =
  "font-serif text-[13px] font-bold uppercase tracking-[0.07em] text-navy mb-[22px]";
const fieldLabel = "font-serif text-[16px] text-navy mb-1";
const fieldHelper = "font-serif text-[13px] leading-[1.6] text-muted-text";
const textareaClass =
  "w-full resize-y box-border rounded-[10px] border border-field-border bg-field-bg px-4 py-[14px] font-serif text-[15px] leading-[1.65] text-navy outline-none transition-colors duration-150 placeholder:text-faint-text focus:border-teal focus:bg-white";

// Left section-nav items. Overview is the active section shown here.
const NAV_ITEMS = [
  {
    key: "overview",
    label: "Overview",
    icon: (
      <>
        <path d="M2 7l8.5-4.5a3 3 0 0 1 3 0L22 7" />
        <path d="M4 9v8a3 3 0 0 0 1.6 2.6L11 22a2 2 0 0 0 2 0l5.4-2.4A3 3 0 0 0 20 17V9" />
      </>
    ),
  },
  {
    key: "documents",
    label: "Documents",
    icon: (
      <>
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
      </>
    ),
  },
  {
    key: "questions",
    label: "Open Questions",
    icon: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M9.5 9a2.5 2.5 0 0 1 4.5 1.5c0 1.5-2 2-2 3.5" />
        <line x1="12" y1="17" x2="12" y2="17" />
      </>
    ),
  },
  {
    key: "preferences",
    label: "Preferences",
    icon: (
      <>
        <path d="M20 7h-9" />
        <path d="M14 17H5" />
        <circle cx="17" cy="17" r="3" />
        <circle cx="7" cy="7" r="3" />
      </>
    ),
  },
] as const;

export default function LabContextPage() {
  const [uploadedFiles, setUploadedFiles] = useState<StagedFile[]>([]);
  const [openQuestions, setOpenQuestions] = useState("");
  const [miscNotes, setMiscNotes] = useState("");
  const [activeSection, setActiveSection] = useState<string>("overview");
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const addFiles = (files: FileList | null) => {
    if (!files) return;
    const staged = Array.from(files).map((file) => ({
      id: `${file.name}-${file.size}-${file.lastModified}-${Math.random()
        .toString(36)
        .slice(2)}`,
      name: file.name,
      size: file.size,
      file,
    }));
    setUploadedFiles((prev) => [...prev, ...staged]);
  };

  const removeFile = (id: string) =>
    setUploadedFiles((prev) => prev.filter((f) => f.id !== id));

  const handleSave = () => {
    // TODO: POST files + text fields to the lab-context endpoint once it's live.
    // eslint-disable-next-line no-console
    console.log("Save lab context", {
      files: uploadedFiles.map((f) => f.file),
      openQuestions,
      miscNotes,
    });
  };

  const handleCancel = () => {
    setUploadedFiles([]);
    setOpenQuestions("");
    setMiscNotes("");
  };

  return (
    <div className="flex h-screen flex-col">
      <TopNav active="labContext" />

      <div className="flex h-[calc(100vh-56px)] bg-page-bg">
        {/* Left section nav */}
        <aside className="box-border w-[248px] flex-shrink-0 border-r border-field-border bg-sidebar-bg px-4 py-7">
          <div className="mb-[14px] px-3 font-serif text-[12px] uppercase tracking-[0.1em] text-muted-text">
            Lab Context
          </div>
          <nav className="flex flex-col gap-[3px]">
            {NAV_ITEMS.map((item) => {
              const isActive = activeSection === item.key;
              return (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => setActiveSection(item.key)}
                  className={`flex items-center gap-[11px] rounded-[7px] px-3 py-[9px] text-left font-serif text-[15px] transition-colors duration-150 ${
                    isActive
                      ? "bg-navy text-pale-ice"
                      : "text-slate-text hover:bg-sidebar-hover"
                  }`}
                >
                  <svg
                    width="17"
                    height="17"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.7"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="flex-shrink-0"
                    aria-hidden="true"
                  >
                    {item.icon}
                  </svg>
                  <span>{item.label}</span>
                </button>
              );
            })}
          </nav>
        </aside>

        {/* Main panel */}
        <main className="lc-scroll box-border flex-1 overflow-y-auto pb-20 pt-14">
          <div className="mx-auto box-border max-w-[760px] px-14">
            {/* Header */}
            <h1 className="mb-[6px] font-serif text-[30px] text-navy">
              Lab Context
            </h1>
            <p className="mb-10 font-serif text-[14px] leading-[1.6] text-muted-text">
              Give the system the background it needs to surface papers that
              matter to your lab. This context shapes what's flagged for you.
            </p>

            {/* Section 1 — Reference Documents */}
            <h2 className={sectionEyebrow}>Reference Documents</h2>
            <div className="flex items-start justify-between gap-10 pb-7">
              <div className="flex-1">
                <div className={fieldLabel}>Upload files</div>
                <p className={fieldHelper}>
                  Add prior papers, grant proposals, or lab notes. PDF, DOCX, or
                  TXT.
                </p>
              </div>
              <div className="w-[300px] flex-shrink-0">
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  className="hidden"
                  onChange={(e) => {
                    addFiles(e.target.files);
                    e.target.value = "";
                  }}
                />
                <div
                  role="button"
                  tabIndex={0}
                  onClick={() => fileInputRef.current?.click()}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      fileInputRef.current?.click();
                    }
                  }}
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDragOver(true);
                  }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={(e) => {
                    e.preventDefault();
                    setDragOver(false);
                    addFiles(e.dataTransfer.files);
                  }}
                  className={`cursor-pointer rounded-[10px] border-[1.5px] border-dashed px-5 py-[26px] text-center transition-colors duration-200 ${
                    dragOver
                      ? "border-teal bg-[#E9F2EC]"
                      : "border-dropzone-border bg-field-bg hover:border-teal hover:bg-[#E9F2EC]"
                  }`}
                >
                  <svg
                    width="26"
                    height="26"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#287858"
                    strokeWidth="1.6"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="mx-auto mb-[10px]"
                    aria-hidden="true"
                  >
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                    <polyline points="17 8 12 3 7 8" />
                    <line x1="12" y1="3" x2="12" y2="15" />
                  </svg>
                  <div className="font-serif text-[14px] text-navy">
                    Drag files here or{" "}
                    <span className="text-teal underline">browse</span>
                  </div>
                </div>

                {/* File list */}
                {uploadedFiles.length > 0 && (
                  <div className="mt-3 flex flex-col gap-[7px]">
                    {uploadedFiles.map((f) => (
                      <div
                        key={f.id}
                        className="flex items-center gap-[9px] rounded-[8px] border border-[#DCE7E1] bg-white px-[11px] py-2"
                      >
                        <svg
                          width="15"
                          height="15"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="#287858"
                          strokeWidth="1.7"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          className="flex-shrink-0"
                          aria-hidden="true"
                        >
                          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                          <polyline points="14 2 14 8 20 8" />
                        </svg>
                        <div className="min-w-0 flex-1 truncate font-serif text-[13px] text-navy">
                          {f.name}
                        </div>
                        <div className="flex-shrink-0 font-serif text-[12px] text-faint-text">
                          {formatSize(f.size)}
                        </div>
                        <button
                          type="button"
                          onClick={() => removeFile(f.id)}
                          aria-label={`Remove ${f.name}`}
                          className="flex-shrink-0 px-[2px] text-[18px] leading-none text-faint-text transition-colors hover:text-navy"
                        >
                          ×
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="mb-9 h-px bg-divider" />

            {/* Section 2 — Open Questions */}
            <h2 className={sectionEyebrow}>Open Questions</h2>
            <div className="mb-2">
              <div className={fieldLabel}>Relevant open questions</div>
              <p className={`${fieldHelper} mb-[14px]`}>
                List the questions your lab is actively trying to answer. Papers
                that speak to these get prioritised.
              </p>
              <textarea
                value={openQuestions}
                onChange={(e) => setOpenQuestions(e.target.value)}
                placeholder={
                  "e.g. What mechanism drives PSL energy transfer at low temperatures?\nDoes the equatorial curvature anomaly replicate across hemispheres?"
                }
                className={`${textareaClass} min-h-[130px]`}
              />
            </div>

            <div className="my-9 h-px bg-divider" />

            {/* Section 3 — Additional Notes */}
            <h2 className={sectionEyebrow}>Additional Notes</h2>
            <div className="mb-8">
              <div className={fieldLabel}>Miscellaneous</div>
              <p className={`${fieldHelper} mb-[14px]`}>
                Anything else worth knowing — collaborators, methods you favour,
                journals you trust, topics to avoid.
              </p>
              <textarea
                value={miscNotes}
                onChange={(e) => setMiscNotes(e.target.value)}
                placeholder="e.g. We collaborate closely with the Hertz lab at Stanford. Prefer empirical over purely theoretical work. Skip anything paywalled behind Elsevier."
                className={`${textareaClass} min-h-[110px]`}
              />
            </div>

            {/* Footer actions */}
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={handleCancel}
                className="rounded-[8px] border border-[#B6CBC0] bg-transparent px-5 py-[9px] font-serif text-[14px] text-slate-text transition-colors hover:bg-[#E4EFE9]"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSave}
                className="rounded-[8px] border border-navy bg-navy px-[22px] py-[9px] font-serif text-[14px] text-pale-ice transition-colors hover:bg-navy-mid"
              >
                Save context
              </button>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
