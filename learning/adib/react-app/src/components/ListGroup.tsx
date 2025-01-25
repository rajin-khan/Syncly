import { useState } from "react";

function ListGroup() {
  let items = ["New York", "San Francisco", "Toky", "London", "Paris"];

  //Hook
  const [selectedIndex, setSelectedIndex] = useState(-1);

  //below, we learn how true && 1 = 1, or true && 'rajin' = 'rajin', and false && 'rajin' = false
  //this is often used in conditional rendering.
  return (
    <>
      <h1>List</h1>
      {items.length === 0 && <p>No item found</p>}
      <ul className="list-group">
        {items.map((item, index) => (
          <li
            className={
              selectedIndex === index
                ? "list-group-item active"
                : "list-group-item"
            }
            key={item}
            onClick={() => {
              setSelectedIndex(index);
            }}
          >
            {item}
          </li>
        ))}
      </ul>
    </>
  );
}

export default ListGroup;
