export const stations = ['集泉一站','一泵站','二泵站','三泵站','四泵站','平定侧入口']
export const alarmRows = [
  { level:'高', station:'二泵站', metric:'出水流量', value:'812 m³/h', threshold:'≥ 1,000', time:'10:42', status:'未确认', relation:'关联下游片区压力下降' },
  { level:'中', station:'四泵站', metric:'2号泵电流', value:'68 A', threshold:'≤ 60 A', time:'10:18', status:'未确认', relation:'' },
  { level:'低', station:'三泵站', metric:'水位', value:'3.2 m', threshold:'≥ 3.5', time:'09:56', status:'已确认', relation:'' },
]
export const telemetry = Array.from({length: 24}, (_, i) => ({ time:`${String(i).padStart(2,'0')}:00`, flow: 1120 + Math.round(Math.sin(i/2)*90), pressure: 0.72 + Math.sin(i/3)*0.06, level: 3.7 + Math.cos(i/3)*.18 }))
export const areas = [
  { name:'平定城区', station:'四泵站', supply:9200, demand:9800, pressure:.38, tank:62, risk:'中' },
  { name:'东部片区', station:'三泵站', supply:5600, demand:5200, pressure:.43, tank:78, risk:'低' },
  { name:'西部片区', station:'二泵站', supply:4100, demand:4700, pressure:.31, tank:45, risk:'高' },
]
