import { useState } from "react";
import styles from './ListGroup.module.css'

interface Props {
    items: string[];
    heading: string;
    onSelectItem: (item: string) => void
}

function ListGroup({items, heading, onSelectItem}: Props) {

  //Hook
  const [selectedIndex, setSelectedIndex] = useState(-1);

  //below, we learn how true && 1 = 1, or true && 'rajin' = 'rajin', and false && 'rajin' = false
  //this is often used in conditional rendering.
  return (
    <>
      <h1>{heading}</h1>
      {items.length === 0 && <p>No item found</p>}
      <ul className={[styles.listGroup, styles.container].join(' ')}>
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
              onSelectItem(item);
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
