export type AvailableSlot = {
  id: number;
  doctor_id: number;
  start_time: string;
  end_time: string;
  status: string;
};

export type Doctor = {
  id: number;
  name: string;
  speciality: string;
  experience_years: number;
  available_slots: AvailableSlot[];
};

export type Appointment = {
  id: number;
  patient_phone: string;
  doctor_name: string;
  slot_start: string | null;
  slot_end: string | null;
  status: string;
};

export type LiveEvent = {
  topic: string;
  data: {
    appointment_id?: number;
    doctor_id?: number;
    slot_id?: number;
    [key: string]: unknown;
  };
  timestamp: string;
};

export type TranscriptEntry = {
  id: string;
  role: "user" | "assistant";
  text: string;
  final: boolean;
};