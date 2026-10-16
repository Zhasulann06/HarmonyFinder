export type Interval = 'major_third' | 'minor_third' | 'perfect_fourth' | 'perfect_fifth' | 'octave' | 'diatonic_third' | 'diatonic_sixth';
export type Scale = 'major' | 'natural_minor';
export type Mode = 'chromatic' | 'scale-aware';
export type InputMode = 'full_song' | 'vocals_only';
export type OutputMode = 'piano' | 'vocal';
export interface ProcessingModes { input_mode: InputMode; output_mode: OutputMode }
export interface HarmonySettings { interval: Interval; direction: 'above' | 'below'; key: string; scale: Scale; mode: Mode }
export interface MixSettings { instrumental_gain: number; lead_vocal_gain: number; harmony_gain: number }
export interface SignalLevels { peak: number; rms: number; duration_seconds: number; sample_rate: number; channels: number; clipping_risk: boolean }
export interface MixDiagnostics { mode: 'stems' | 'original_legacy' | 'original_fallback'; input_levels: Record<string, SignalLevels>; gained_levels: Record<string, SignalLevels>; pre_protection: SignalLevels; output: SignalLevels; headroom_gain: number; gains: Record<string, number>; harmony_to_lead_rms_db: number | null; warning: string | null }
export interface JobStatus { audio_id: string; status: 'queued' | 'processing' | 'completed' | 'failed'; error?: string | null }
export interface UploadResponse extends JobStatus { duration_seconds: number }
export interface Timing { start_time: number; end_time: number; duration: number }
export interface PitchNote extends Timing { midi_note: number; note_name: string; midi_pitch: number; median_pitch_hz: number; pitch_deviation_cents: number; confidence: number | null; voiced_probability: number | null }
export interface PitchAnalysis { detector: string; duration_seconds: number; sample_rate: number; hop_length: number; frame_length: number; fmin_hz: number; fmax_hz: number; frames: { time_seconds: number; f0_hz: number | null; midi_pitch: number | null; voiced: boolean; voiced_probability: number | null }[]; notes: PitchNote[] }
export interface QuantizedNote extends Timing { original_midi_pitch: number; corrected_midi_pitch: number; original_note_name: string; corrected_note_name: string; correction_cents: number; median_pitch_hz: number; confidence: number | null; voiced_probability: number | null }
export interface QuantizedMelody { mode: Mode; key: string | null; scale: Scale | null; duration_seconds: number; notes: QuantizedNote[] }
export interface HarmonyNote extends Timing { original_midi_note: number; harmony_midi_note: number; original_note_name: string; harmony_note_name: string }
export interface HarmonyMelody { interval: Interval; direction: 'above' | 'below'; key: string | null; scale: Scale | null; duration_seconds: number; notes: HarmonyNote[] }
export type RenderFile = 'harmony.mid' | 'harmony_piano.wav' | 'harmony_vocals.wav' | 'preview_mix.wav';
export interface RenderResponse { audio_id: string; status: 'completed'; sample_rate: number; channels: number; duration_seconds: number; files: Partial<Record<RenderFile, string>>; mix_diagnostics?: MixDiagnostics | null; output_mode?: OutputMode; warning?: string | null }
export interface GenerationResult { audioId: string; harmony: HarmonyMelody; render: RenderResponse }
