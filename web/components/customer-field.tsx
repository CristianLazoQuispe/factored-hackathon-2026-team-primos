import type { DemoCustomer } from "@/lib/customer";

import "./customer-field.css";

// The "Cliente" field of the header: free text, with the customers the API offers as suggestions.
export function CustomerField({
  value,
  onChange,
  customers,
}: {
  value: string;
  onChange: (value: string) => void;
  customers: DemoCustomer[];
}) {
  return (
    <label className="customer-field">
      Cliente
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        list="demo-customers"
        placeholder="Tu ID de cliente"
        spellCheck={false}
        autoComplete="off"
      />
      <datalist id="demo-customers">
        {customers.map((c) => (
          <option key={c.customer_id} value={c.customer_id} label={`${c.first_name} · ${c.country} · ${c.segment}`} />
        ))}
      </datalist>
    </label>
  );
}
