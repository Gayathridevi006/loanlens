import axios from 'axios';
const defaultApiUrl=`${window.location.protocol}//${window.location.hostname}:8000`;
export const api=axios.create({baseURL:import.meta.env.VITE_API_URL||defaultApiUrl});
export type Application={id:string;applicant_name:string;email:string;loan_type:string;loan_amount:number;income:number;credit_score:number;dti:number;employment_years:number;existing_loans:number;comments:string;status:'APPROVE'|'REVIEW'|'REJECT';risk_score:number;fraud_score:number;sentiment:string;sentiment_confidence:number;explanation:string;ai_summary:string;source_file:string;processing_log:string[];created_at:string};
