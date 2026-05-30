export function BotPanel() {
  const buttons = [
    // Row 0
    [
      { emoji: "▶️", label: "Play", accent: true },
      { emoji: "⏮️", label: "Prev" },
      { emoji: "⏸️", label: "Pause" },
      { emoji: "⏭️", label: "Skip" },
      { emoji: "📋", label: "Queue" },
    ],
    // Row 1
    [
      { emoji: "🔄", label: "Restart" },
      { emoji: "⏪", label: "Back" },
      { emoji: "❤️", label: "Like", danger: true },
      { emoji: "⏩", label: "FF" },
      { emoji: "🔊", label: "Volume" },
    ],
    // Row 2
    [
      { emoji: "🎶", label: "Playlist" },
      { emoji: "🔀", label: "Shuffle" },
      { emoji: "🔵", label: "Autoplay", blue: true },
      { emoji: "🔁", label: "Loop" },
      { emoji: "🛟", label: "Help" },
    ],
  ];

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#1e1f22]">
      <div className="w-[480px] rounded-xl overflow-hidden shadow-2xl border border-[#1e1f22]">

        {/* Banner */}
        <div className="relative h-28 bg-gradient-to-br from-[#5865f2] via-[#7c3aed] to-[#eb459e] flex items-end p-4">
          <div className="absolute inset-0 opacity-20"
            style={{ backgroundImage: "repeating-linear-gradient(45deg,transparent,transparent 10px,rgba(255,255,255,.05) 10px,rgba(255,255,255,.05) 20px)" }} />
          <div className="flex items-center gap-3 relative z-10">
            <div className="w-12 h-12 rounded-full bg-[#5865f2] border-4 border-[#2b2d31] flex items-center justify-center shadow-lg text-2xl">
              🎵
            </div>
            <div>
              <p className="text-white font-bold text-base leading-tight">Rhythm</p>
              <p className="text-white/70 text-xs">Advanced Music Bot</p>
            </div>
          </div>
          {/* Waveform decoration */}
          <div className="absolute right-4 bottom-3 flex items-end gap-[3px] opacity-40">
            {[12, 20, 10, 28, 16, 8, 24, 14, 22, 10, 18].map((h, i) => (
              <div key={i} className="w-[3px] rounded-full bg-white" style={{ height: h }} />
            ))}
          </div>
        </div>

        {/* Body */}
        <div className="bg-[#2b2d31] px-5 pt-4 pb-5">

          {/* Description */}
          <p className="text-[#b5bac1] text-[13px] leading-snug mb-4">
            Click the button, and any empty bot will connect to your channel without any commands — it is managed through this panel.
          </p>

          {/* Divider */}
          <div className="border-t border-[#3b3d44] mb-4" />

          {/* Button rows */}
          <div className="flex flex-col gap-2">
            {buttons.map((row, ri) => (
              <div key={ri} className="flex gap-2">
                {row.map((btn) => (
                  <button
                    key={btn.label}
                    title={btn.label}
                    className={[
                      "flex-1 h-10 rounded-[4px] flex items-center justify-center text-xl",
                      "transition-all duration-100 active:scale-95 select-none",
                      btn.accent
                        ? "bg-[#248046] hover:bg-[#1a6334] text-white"
                        : btn.danger
                        ? "bg-[#da373c] hover:bg-[#a12828] text-white"
                        : btn.blue
                        ? "bg-[#4752c4] hover:bg-[#3a45a8] text-white"
                        : "bg-[#4e5058] hover:bg-[#5c5f66] text-white",
                    ].join(" ")}
                  >
                    {btn.emoji}
                  </button>
                ))}
              </div>
            ))}
          </div>

          {/* Footer */}
          <div className="mt-4 flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full bg-[#23a55a]" />
            <span className="text-[#949ba4] text-[11px]">🎵 Rhythm • Advanced Music Bot</span>
          </div>
        </div>
      </div>
    </div>
  );
}
